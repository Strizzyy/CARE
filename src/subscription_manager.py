from typing import List, Dict, Optional
from datetime import datetime
import uuid
import logging
from data_handler import MongoDBHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("logs/subscription_manager.log"), logging.StreamHandler()]
)

class SubscriptionManager:
    def __init__(self, data_handler: MongoDBHandler):
        self.data_handler = data_handler

    async def create_subscription(self, subscription_data: Dict) -> Dict:
        """Create a new subscription for a customer."""
        customer_id = subscription_data.get("customer_id")
        logging.info(f"Creating subscription for customer {customer_id}")
        try:
            await self.data_handler.add_subscription(subscription_data)
            logging.info(f"Subscription {subscription_data['subscription_id']} created successfully")
            return subscription_data
        except Exception as e:
            logging.error(f"Error creating subscription for customer {customer_id}: {e}")
            raise

    async def get_customer_subscriptions(self, customer_id: str) -> List[Dict]:
        """Retrieve all subscriptions for a customer."""
        logging.info(f"Fetching subscriptions for customer {customer_id}")
        try:
            subscriptions = await self.data_handler.get_customer_subscriptions(customer_id)
            return subscriptions
        except Exception as e:
            logging.error(f"Error fetching subscriptions for customer {customer_id}: {e}")
            return []

    async def cancel_subscription(self, subscription_id: str) -> bool:
        """Cancel a subscription by setting its status to 'cancelled'."""
        logging.info(f"Cancelling subscription {subscription_id}")
        try:
            result = await self.data_handler.update_subscription(subscription_id, {"status": "cancelled"})
            if result:
                logging.info(f"Subscription {subscription_id} cancelled successfully")
                return True
            else:
                logging.warning(f"Subscription {subscription_id} not found")
                return False
        except Exception as e:
            logging.error(f"Error cancelling subscription {subscription_id}: {e}")
            return False

    async def get_notification(self, subscription_id: str) -> Optional[Dict]:
        """Generate a notification for a subscription based on delivery date."""
        logging.info(f"Generating notification for subscription {subscription_id}")
        try:
            subscription = await self.data_handler.subscriptions.find_one({"subscription_id": subscription_id, "status": "active"})
            if subscription:
                delivery_date = subscription.get("delivery_date")
                if delivery_date:
                    try:
                        next_delivery = datetime.strptime(delivery_date, "%Y-%m-%d").date()
                        current_date = datetime.now().date()
                        days_until = (next_delivery - current_date).days
                        items = ", ".join([item["name"] for item in subscription["items"]])
                        subscription_type = subscription.get("subscription_type", "weekly")
                        if days_until == 1:
                            return {
                                "message": f"Reminder: Your planned order {subscription_id} will restock {items} tomorrow on {delivery_date} ({subscription_type}).",
                                "subscription_id": subscription_id,
                                "delivery_date": delivery_date
                            }
                        elif 2 <= days_until <= 3:
                            return {
                                "message": f"Reminder: Your planned order {subscription_id} will restock {items} on {delivery_date} ({subscription_type}).",
                                "subscription_id": subscription_id,
                                "delivery_date": delivery_date
                            }
                    except ValueError as e:
                        logging.error(f"Invalid date format for subscription {subscription_id}: {e}")
                        return None
                else:
                    logging.warning(f"No delivery date for subscription {subscription_id}")
                    return None
            else:
                logging.warning(f"Subscription {subscription_id} not found or inactive")
                return None
        except Exception as e:
            logging.error(f"Error generating notification for subscription {subscription_id}: {e}")
            return None