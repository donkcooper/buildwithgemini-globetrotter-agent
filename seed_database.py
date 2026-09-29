from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-01-f7a1918bd440"

db = firestore.Client(project=PROJECT_ID)

destinations = [
    {
        "id": "dest_kyoto",
        "name": "Kyoto Cultural & Temple Exploration",
        "city": "Kyoto",
        "country": "Japan",
        "category": "Culture",
        "rating": 4.9,
        "price_per_day_usd": 150,
        "description": "Explore historic temples, serene bamboo groves, traditional tea houses, and Fushimi Inari shrine.",
        "recommended_activities": ["Visit Fushimi Inari", "Arashiyama Bamboo Grove", "Gion Tea Ceremony"],
    },
    {
        "id": "dest_paris",
        "name": "Paris Art & Culinary Discovery",
        "city": "Paris",
        "country": "France",
        "category": "Culinary",
        "rating": 4.8,
        "price_per_day_usd": 220,
        "description": "Experience world-class museums, artisan bakeries, Seine river cruises, and Montmartre cafes.",
        "recommended_activities": ["Louvre Museum Tour", "Pastry Tasting in Le Marais", "Eiffel Tower Sunset"],
    },
    {
        "id": "dest_banff",
        "name": "Banff Alpine Nature & Wilderness",
        "city": "Banff",
        "country": "Canada",
        "category": "Nature",
        "rating": 4.9,
        "price_per_day_usd": 180,
        "description": "Breathtaking turquoise glacial lakes, mountain hiking, wildlife spotting, and hot springs.",
        "recommended_activities": ["Lake Louise Kayaking", "Johnston Canyon Hike", "Banff Upper Hot Springs"],
    },
    {
        "id": "dest_santorini",
        "name": "Santorini Coastal Escape",
        "city": "Santorini",
        "country": "Greece",
        "category": "Beach",
        "rating": 4.7,
        "price_per_day_usd": 250,
        "description": "Iconic whitewashed cliffside villages, Aegean sea views, volcanic beaches, and wine tasting.",
        "recommended_activities": ["Oia Sunset Viewpoint", "Catamaran Cruise", "Santo Wines Tasting"],
    },
]


def seed():
    print(f"Seeding Firestore collection 'destinations' in project {PROJECT_ID}...")
    collection_ref = db.collection("destinations")
    for item in destinations:
        doc_id = item["id"]
        collection_ref.document(doc_id).set(item)
        print(f"  - Seeded destination: {doc_id} ({item['name']})")
    print("Seeding complete!")


if __name__ == "__main__":
    seed()
