from motor.motor_asyncio import AsyncIOMotorClient
from typing import Dict, List, Optional
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("logs/data_handler.log"), logging.StreamHandler()]
)

class MongoDBHandler:
    def __init__(self, mongodb_uri: str):
        self.mongodb_uri = mongodb_uri
        self.client = None
        self.db = None
        self.collections = {
            "customers": None,
            "orders": None,
            "payments": None,
            "subscriptions": None,
            "escalations": None
        }

    async def initialize(self):
        try:
            self.client = AsyncIOMotorClient(self.mongodb_uri, serverSelectionTimeoutMS=5000)
            self.db = self.client["care_db"]
            for coll_name, coll in self.collections.items():
                self.collections[coll_name] = self.db[coll_name]
            await self._create_indexes()
            await self.client.admin.command('ping')
            logging.info("Connected to MongoDB Atlas")
        except Exception as e:
            logging.error(f"Failed to connect to MongoDB Atlas: {e}")
            raise

    async def _create_indexes(self):
        await self.collections["customers"].create_index("customer_id")
        await self.collections["orders"].create_index("order_id")
        await self.collections["payments"].create_index("payment_id")
        await self.collections["subscriptions"].create_index("subscription_id")
        await self.collections["escalations"].create_index("case_id")

    def _convert_objectid(self, data: Dict) -> Dict:
        if not data:
            return data
        if '_id' in data and hasattr(data['_id'], '__str__'):
            data['_id'] = str(data['_id'])
        for key, value in data.items():
            if isinstance(value, dict):
                data[key] = self._convert_objectid(value)
            elif isinstance(value, list):
                data[key] = [self._convert_objectid(item) if isinstance(item, dict) else item for item in value]
        return data

    async def get_customer(self, customer_id: str) -> Optional[Dict]:
        doc = await self.collections["customers"].find_one({"customer_id": customer_id})
        return self._convert_objectid(doc) if doc else None

    async def get_customers(self) -> List[Dict]:
        cursor = self.collections["customers"].find()
        docs = [doc async for doc in cursor]
        return [self._convert_objectid(doc) for doc in docs]

    async def get_customer_orders(self, customer_id: str) -> List[Dict]:
        cursor = self.collections["orders"].find({"customer_id": customer_id})
        docs = [doc async for doc in cursor]
        return [self._convert_objectid(doc) for doc in docs]

    async def get_order(self, order_id: str) -> Optional[Dict]:
        doc = await self.collections["orders"].find_one({"order_id": order_id})
        return self._convert_objectid(doc) if doc else None

    async def get_order_amount(self, order_id: str) -> Optional[float]:
        order = await self.collections["orders"].find_one({"order_id": order_id})
        return order.get("total_amount") if order else None

    async def get_payment(self, payment_id: str) -> Optional[Dict]:
        doc = await self.collections["payments"].find_one({"payment_id": payment_id})
        return self._convert_objectid(doc) if doc else None

    async def get_customer_payments(self, customer_id: str) -> List[Dict]:
        cursor = self.collections["payments"].find({"customer_id": customer_id})
        docs = [doc async for doc in cursor]
        return [self._convert_objectid(doc) for doc in docs]

    async def get_order_payment(self, order_id: str) -> Optional[Dict]:
        doc = await self.collections["payments"].find_one({"order_id": order_id})
        return self._convert_objectid(doc) if doc else None

    async def update_wallet_balance(self, customer_id: str, new_balance: float) -> bool:
        result = await self.collections["customers"].update_one(
            {"customer_id": customer_id},
            {"$set": {"wallet_balance": new_balance}}
        )
        return result.modified_count > 0

    async def get_failed_payments(self, customer_id: str) -> List[Dict]:
        cursor = self.collections["payments"].find({"customer_id": customer_id, "status": "failed"})
        docs = [doc async for doc in cursor]
        return [self._convert_objectid(doc) for doc in docs]

    async def update_payments(self, payments: List[Dict]) -> None:
        for payment in payments:
            await self.collections["payments"].update_one(
                {"payment_id": payment["payment_id"]},
                {"$set": payment},
                upsert=True
            )

    async def get_customer_subscriptions(self, customer_id: str) -> List[Dict]:
        cursor = self.collections["subscriptions"].find({"customer_id": customer_id})
        docs = [doc async for doc in cursor]
        return [self._convert_objectid(doc) for doc in docs]

    async def add_subscription(self, subscription: Dict) -> None:
        await self.collections["subscriptions"].insert_one(subscription)

    async def update_subscription(self, subscription_id: str, updates: Dict) -> bool:
        result = await self.collections["subscriptions"].update_one(
            {"subscription_id": subscription_id},
            {"$set": updates}
        )
        return result.modified_count > 0

    async def add_escalation(self, case_id: str, customer_id: str, issue_details: str) -> bool:
        escalation = {
            "case_id": case_id,
            "customer_id": customer_id,
            "issue_details": issue_details,
            "status": "pending",
            "escalation_time": datetime.now().isoformat()
        }
        await self.collections["escalations"].insert_one(escalation)
        return True

    async def get_escalation(self, case_id: str) -> Optional[Dict]:
        doc = await self.collections["escalations"].find_one({"case_id": case_id})
        return self._convert_objectid(doc) if doc else None

    async def get_customer_escalations(self, customer_id: str) -> List[Dict]:
        cursor = self.collections["escalations"].find({"customer_id": customer_id})
        docs = [doc async for doc in cursor]
        return [self._convert_objectid(doc) for doc in docs]

    async def get_all_escalations(self) -> List[Dict]:
        cursor = self.collections["escalations"].find()
        docs = [doc async for doc in cursor]
        return [self._convert_objectid(doc) for doc in docs]

    async def update_escalation_status(self, case_id: str, status: str) -> bool:
        result = await self.collections["escalations"].update_one(
            {"case_id": case_id},
            {"$set": {"status": status, "resolved_at": datetime.now().isoformat()}}
        )
        return result.modified_count > 0

    async def resolve_escalation(self, case_id: str, resolution: Dict) -> bool:
        result = await self.collections["escalations"].update_one(
            {"case_id": case_id},
            {"$set": {
                "status": "resolved",
                "resolution": resolution,
                "resolved_at": datetime.now().isoformat()
            }}
        )
        return result.modified_count > 0

    async def close(self):
        if self.client:
            self.client.close()