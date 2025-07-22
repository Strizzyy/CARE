import json
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
import asyncio

# Load environment variables
load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI")
DATA_PATH = os.getenv("DATA_PATH", "mock_data")

# Connect to MongoDB
client = AsyncIOMotorClient(MONGODB_URI)
db = client["care_db"]

async def insert_data(collection_name, json_file):
    try:
        with open(json_file, "r") as f:
            data = json.load(f)
        collection = db[collection_name]
        # Clear existing data (optional, remove if you want to append)
        await collection.delete_many({})
        # Insert new data
        if collection_name == "escalations":
            # Transform escalations dictionary into a list of documents
            documents = [{"case_id": k, **v} for k, v in data["escalations"].items()]
        else:
            documents = data[collection_name]
        if documents:
            await collection.insert_many(documents)
            print(f"Populated {collection_name} with {len(documents)} documents.")
        else:
            print(f"No documents to insert in {collection_name}.")
    except FileNotFoundError:
        print(f"File {json_file} not found.")
    except Exception as e:
        print(f"Error populating {collection_name}: {str(e)}")

async def populate():
    # Populate each collection
    await insert_data("customers", f"{DATA_PATH}/customers.json")
    await insert_data("orders", f"{DATA_PATH}/orders.json")
    await insert_data("payments", f"{DATA_PATH}/payments.json")
    await insert_data("subscriptions", f"{DATA_PATH}/subscriptions.json")
    if os.path.exists(f"{DATA_PATH}/calendar_events.json"):
        await insert_data("events", f"{DATA_PATH}/calendar_events.json")
    else:
        print("Skipping events: calendar_events.json not found.")
    await insert_data("escalations", f"{DATA_PATH}/escalations.json")

if __name__ == "__main__":
    asyncio.run(populate())
    print("Data population completed!")
    client.close()
