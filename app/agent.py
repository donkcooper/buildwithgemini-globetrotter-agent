# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os
import urllib.request
import uuid
from zoneinfo import ZoneInfo

from pathlib import Path

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types

from app.a2ui_utils import a2ui_callback

PROJECT_ID = "qwiklabs-gcp-01-f7a1918bd440"
BUCKET_NAME = "globetrotter-assets-qwiklabs-gcp-01-f7a1918bd440"

db = firestore.Client(project=PROJECT_ID)
storage_client = storage.Client(project=PROJECT_ID)
genai_client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")

EXCHANGE_RATE_API_KEY = os.environ.get("EXCHANGE_RATE_API_KEY", "")

# Load Agent Engine resource name from deployment_metadata.json if available
metadata_path = Path(__file__).parent.parent / "deployment_metadata.json"
agent_engine_resource_name = None
if metadata_path.exists():
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
            agent_engine_resource_name = meta.get("remote_agent_runtime_id")
    except Exception:
        pass

code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=agent_engine_resource_name
)


async def generate_memories_callback(callback_context: CallbackContext):
    """WRITE callback: sends turn events to Vertex AI Memory Bank for background extraction."""
    try:
        await callback_context.add_session_to_memory()
    except Exception:
        pass
    return None


def search_destinations(city: str = "", category: str = "") -> str:
    """Searches travel destinations from the Firestore database.

    Args:
        city: Optional city name filter (e.g. 'Kyoto', 'Paris').
        category: Optional travel category filter (e.g. 'Culture', 'Culinary', 'Nature', 'Beach').

    Returns:
        A formatted list of matching destination items with details.
    """
    collection_ref = db.collection("destinations")
    docs = collection_ref.stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        if city and city.lower() not in data.get("city", "").lower():
            continue
        if category and category.lower() not in data.get("category", "").lower():
            continue
        results.append(data)

    if not results:
        return "No matching destinations found in the database."

    output_lines = [f"Found {len(results)} destination(s):"]
    for item in results:
        output_lines.append(
            f"- [{item.get('id')}] {item.get('name')} ({item.get('city')}, {item.get('country')}): "
            f"Category: {item.get('category')}, Rating: {item.get('rating')}/5, "
            f"Price: ${item.get('price_per_day_usd')}/day. "
            f"Description: {item.get('description')}"
        )
    return "\n".join(output_lines)


def add_destination(
    destination_id: str,
    name: str,
    city: str,
    country: str,
    category: str,
    price_per_day_usd: int,
    description: str,
    rating: float = 4.5,
) -> str:
    """Adds a new destination or updates an existing destination in the Firestore database.

    Args:
        destination_id: Unique string identifier for the destination (e.g., 'dest_tokyo').
        name: Full title of the destination or tour.
        city: City location.
        country: Country location.
        category: Travel category (e.g. 'Culture', 'Culinary', 'Nature', 'Beach').
        price_per_day_usd: Estimated cost per day in USD.
        description: A brief summary of the destination.
        rating: Optional rating score out of 5.0.

    Returns:
        A success message confirming addition to Firestore.
    """
    item = {
        "id": destination_id,
        "name": name,
        "city": city,
        "country": country,
        "category": category,
        "price_per_day_usd": price_per_day_usd,
        "description": description,
        "rating": rating,
    }
    db.collection("destinations").document(destination_id).set(item)
    return f"Successfully saved destination '{name}' ({destination_id}) to Firestore."


def get_weather(query: str) -> str:
    """Simulates getting weather information for a location.

    Args:
        query: Location string.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: City name.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


def calculate_trip_budget(
    days: int,
    price_per_day_usd: float,
    flight_cost_usd: float = 0.0,
    num_travelers: int = 1,
) -> str:
    """Calculates total estimated budget and breakdown for a travel trip.

    Args:
        days: Number of days for the trip.
        price_per_day_usd: Estimated daily accommodation and activity cost per person in USD.
        flight_cost_usd: Optional flight or transportation cost per person in USD.
        num_travelers: Number of travelers (default 1).

    Returns:
        A detailed cost breakdown and total trip budget string.
    """
    stay_cost = days * price_per_day_usd * num_travelers
    transport_cost = flight_cost_usd * num_travelers
    contingency = (stay_cost + transport_cost) * 0.10
    total_budget = stay_cost + transport_cost + contingency

    return (
        f"Trip Budget Breakdown ({days} days, {num_travelers} traveler(s)):\n"
        f"- Daily Stay & Activities (${price_per_day_usd:.2f}/day/person): ${stay_cost:.2f}\n"
        f"- Flights / Transport (${flight_cost_usd:.2f}/person): ${transport_cost:.2f}\n"
        f"- Recommended Contingency (10%): ${contingency:.2f}\n"
        f"Total Estimated Budget: ${total_budget:.2f} USD"
    )


def get_currency_exchange_rate(
    amount: float = 1.0,
    from_currency: str = "USD",
    to_currency: str = "EUR",
) -> str:
    """Fetches real-time currency exchange rates and converts travel funds using the Frankfurter public API.

    Args:
        amount: Monetary amount to convert (default 1.0).
        from_currency: 3-letter source currency code (e.g., 'USD', 'EUR', 'GBP').
        to_currency: 3-letter target currency code (e.g., 'JPY', 'EUR', 'CAD', 'GBP').

    Returns:
        A string with the converted value and current exchange rate.
    """
    from_curr = from_currency.strip().upper()
    to_curr = to_currency.strip().upper()
    url = f"https://api.frankfurter.app/latest?amount={amount}&from={from_curr}&to={to_curr}"

    headers = {"User-Agent": "GlobeTrotterAI/1.0"}
    if EXCHANGE_RATE_API_KEY:
        headers["Authorization"] = f"Bearer {EXCHANGE_RATE_API_KEY}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                rates = data.get("rates", {})
                converted_val = rates.get(to_curr)
                if converted_val is not None:
                    rate_per_unit = converted_val / amount if amount != 0 else 0
                    return (
                        f"{amount:.2f} {from_curr} = {converted_val:.2f} {to_curr} "
                        f"(Rate: 1 {from_curr} = {rate_per_unit:.4f} {to_curr} as of {data.get('date')})"
                    )
                return f"Could not find exchange rate for currency '{to_curr}'."
            return f"Error fetching exchange rate: HTTP {response.status}."
    except Exception as e:
        return f"Unable to fetch exchange rate for {from_curr} to {to_curr}: {str(e)}"


async def generate_destination_image(
    prompt: str,
    tool_context: ToolContext = None,
) -> str:
    """Generates a travel or destination image using gemini-3.1-flash-lite-image model in global region.

    Saves the image as a session artifact and uploads it to the public Cloud Storage bucket.

    Args:
        prompt: Detailed image generation prompt for a travel destination or landmark.

    Returns:
        The public HTTPS URL of the uploaded image in Cloud Storage.
    """
    try:
        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"]
            ),
        )

        image_bytes = None
        mime_type = "image/jpeg"
        if response.candidates and response.candidates[0].content.parts:
            part = response.candidates[0].content.parts[0]
            if hasattr(part, "inline_data") and part.inline_data:
                image_bytes = part.inline_data.data
                if part.inline_data.mime_type:
                    mime_type = part.inline_data.mime_type

        if not image_bytes:
            return "Failed to generate image bytes from model response."

        filename = f"destination_{uuid.uuid4().hex[:8]}.jpg"

        # (1) Save as session artifact if tool_context is provided
        if tool_context and hasattr(tool_context, "save_artifact"):
            artifact_part = types.Part.from_bytes(
                data=image_bytes,
                mime_type=mime_type,
            )
            try:
                await tool_context.save_artifact(
                    filename=filename, artifact=artifact_part
                )
            except Exception as e:
                pass  # Ignore artifact service errors if unconfigured in local test

        # (2) Upload to public Cloud Storage bucket
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
        return public_url
    except Exception as e:
        return f"Error generating image: {str(e)}"


async def generate_destination_video(
    prompt: str,
    tool_context: ToolContext = None,
) -> str:
    """Generates a short travel preview video for a destination using Google's Omni model (gemini-omni-flash-preview) in global region.

    Saves the video as a session artifact and uploads it to the public Cloud Storage bucket.

    Args:
        prompt: Detailed prompt describing the travel video scene or destination preview.

    Returns:
        The public HTTPS URL of the uploaded video in Cloud Storage.
    """
    try:
        interaction = genai_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt,
        )

        video_bytes = None
        if hasattr(interaction, "output_video") and interaction.output_video:
            if hasattr(interaction.output_video, "data") and interaction.output_video.data:
                video_bytes = base64.b64decode(interaction.output_video.data)

        if not video_bytes and hasattr(interaction, "steps"):
            for step in getattr(interaction, "steps", []):
                for content in getattr(step, "content", []):
                    if getattr(content, "type", "") == "video" or getattr(content, "mime_type", "").startswith("video/"):
                        data = getattr(content, "data", None)
                        if data:
                            video_bytes = base64.b64decode(data)

        if not video_bytes:
            return "Failed to generate video bytes from model response."

        filename = f"video_{uuid.uuid4().hex[:8]}.mp4"
        mime_type = "video/mp4"

        # (1) Save video as session artifact if tool_context is provided
        if tool_context and hasattr(tool_context, "save_artifact"):
            artifact_part = types.Part.from_bytes(
                data=video_bytes,
                mime_type=mime_type,
            )
            try:
                await tool_context.save_artifact(
                    filename=filename, artifact=artifact_part
                )
            except Exception:
                pass  # Ignore artifact service errors if unconfigured in local test

        # (2) Upload video bytes directly to public Cloud Storage bucket
        bucket = storage_client.bucket("globetrotter-assets-qwiklabs-gcp-01-f7a1918bd440")
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/globetrotter-assets-qwiklabs-gcp-01-f7a1918bd440/{filename}"
        return public_url
    except Exception as e:
        return f"Error generating video: {str(e)}"


a2ui_schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = a2ui_schema_manager.generate_system_prompt(
    role_description=(
        "You are GlobeTrotter AI, a travel and local concierge assistant. "
        "Use your tools `search_destinations`, `add_destination`, `calculate_trip_budget`, "
        "`get_currency_exchange_rate`, `generate_destination_image`, and `generate_destination_video` to assist travelers. "
        "When performing complex math or custom calculations, write Python code inside a ```python ... ``` block so it executes in your sandbox. "
        "Proactively remember and personalize responses based on the user's travel facts & preferences across sessions (home airport, budget tier, dietary restrictions, preferred activities)."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    code_executor=code_executor,
    tools=[
        PreloadMemoryTool(),
        search_destinations,
        add_destination,
        calculate_trip_budget,
        get_currency_exchange_rate,
        generate_destination_image,
        generate_destination_video,
        get_weather,
        get_current_time,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)

