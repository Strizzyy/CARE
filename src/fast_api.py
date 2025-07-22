from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from nlu_pipeline import NLUPipeline
from subscription_manager import SubscriptionManager
from resolution_engine import ResolutionAgent
from data_handler import MongoDBHandler
from dotenv import load_dotenv
import uuid
import re  # Added for regex
import logging
import os

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("care_api.log"), logging.StreamHandler()]
)

app = FastAPI(title="CARE API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MONGODB_URI = os.getenv("MONGODB_URI")

# Initialize components lazily
data_handler = None
nlu = None
subscription_manager = None
resolution_agent = None

@app.on_event("startup")
async def startup_event():
    global data_handler, nlu, subscription_manager, resolution_agent
    data_handler = MongoDBHandler(MONGODB_URI)
    await data_handler.initialize()
    nlu = NLUPipeline(GROQ_API_KEY, MONGODB_URI)
    subscription_manager = SubscriptionManager(data_handler)
    resolution_agent = ResolutionAgent(data_handler, GEMINI_API_KEY)

@app.on_event("shutdown")
async def shutdown_event():
    global data_handler
    if data_handler:
        await data_handler.close()

class ChatRequest(BaseModel):
    message: str
    customer_id: str

class SubscriptionRequest(BaseModel):
    customer_id: str
    items: list[dict]
    delivery_date: str
    subscription_type: str = "weekly"

@app.get("/health")
async def health_check():
    logging.info("Health check endpoint called.")
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/customers")
async def get_customers():
    try:
        logging.info("Fetching customers via API endpoint.")
        customers = await data_handler.get_customers()
        logging.info(f"Fetched {len(customers)} customers.")
        return {
            "customers": [
                {"customer_id": c["customer_id"], "name": c["name"], "membership": c["membership"], "location": c["location"]}
                for c in customers
            ]
        }
    except Exception as e:
        logging.error(f"Error in get_customers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/customer/{customer_id}")
async def get_customer_info(customer_id: str):
    try:
        logging.info(f"Fetching info for customer {customer_id}.")
        customer = await data_handler.get_customer(customer_id)
        if not customer:
            logging.warning(f"Customer {customer_id} not found.")
            raise HTTPException(status_code=404, detail="Customer not found")
        orders = await data_handler.get_customer_orders(customer_id)
        payments = await data_handler.get_customer_payments(customer_id)
        subscriptions = await data_handler.get_customer_subscriptions(customer_id)
        logging.info(f"Customer {customer_id}: {len(orders)} orders, {len(payments)} payments, {len(subscriptions)} subscriptions.")
        return {
            "customer": customer,
            "orders": orders,
            "payments": payments,
            "subscriptions": subscriptions,
            "summary": {
                "total_orders": len(orders),
                "total_payments": len(payments),
                "total_subscriptions": len(subscriptions),
                "wallet_balance": customer["wallet_balance"]
            }
        }
    except Exception as e:
        logging.error(f"Error in get_customer_info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        customer_id = request.customer_id
        message = request.message
        logging.info(f"Processing chat for {customer_id}: {message}")
        # Example: Fetch order status
        if "where is my order" in message.lower():
            # Extract order ID using regex
            order_id_match = re.search(r'ORD\d{3}', message)
            order_id = order_id_match.group() if order_id_match else None
            logging.info(f"Extracted order_id: {order_id}")
            if not order_id:
                return {"response": "Please provide a valid order ID (e.g., ORD001).", "status": "not_found"}
            order = await data_handler.get_order(order_id)
            logging.info(f"Order data: {order}")
            if not order:
                return {"response": f"Order {order_id} not found.", "status": "not_found"}
            return {"response": f"Order {order_id} is {order.get('status', 'being processed')}.", "status": "in_progress"}
        return {"response": "I can help with that!", "status": "ok"}
    except Exception as e:
        logging.error(f"Error in chat_endpoint for customer {customer_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="I apologize, but I encountered an error. Please try again.")

@app.post("/subscription")
async def create_subscription(request: SubscriptionRequest):
    try:
        if not all([request.customer_id, request.items, request.delivery_date]):
            logging.warning("Create subscription called with missing fields.")
            raise HTTPException(status_code=400, detail="Missing required fields")
        subscription = await subscription_manager.create_subscription(
            request.customer_id, request.items, request.delivery_date, request.subscription_type
        )
        logging.info(f"Subscription {subscription['subscription_id']} created for customer {request.customer_id}.")
        return {
            "message": f"Subscription {subscription['subscription_id']} created successfully",
            "subscription": subscription
        }
    except Exception as e:
        logging.error(f"Error in create_subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/subscriptions/{customer_id}")
async def get_subscriptions(customer_id: str):
    try:
        logging.info(f"Fetching subscriptions for customer {customer_id}.")
        subscriptions = await subscription_manager.get_customer_subscriptions(customer_id)
        logging.info(f"Found {len(subscriptions)} subscriptions for customer {customer_id}.")
        return {"subscriptions": subscriptions}
    except Exception as e:
        logging.error(f"Error in get_subscriptions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/subscription/cancel/{subscription_id}")
async def cancel_subscription(subscription_id: str):
    try:
        logging.info(f"Attempting to cancel subscription {subscription_id}.")
        if await subscription_manager.cancel_subscription(subscription_id):
            logging.info(f"Subscription {subscription_id} cancelled.")
            return {"message": f"Subscription {subscription_id} cancelled"}
        logging.warning(f"Subscription {subscription_id} not found for cancellation.")
        raise HTTPException(status_code=404, detail="Subscription not found")
    except Exception as e:
        logging.error(f"Error in cancel_subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/subscription/notifications/{customer_id}")
async def get_subscription_notifications(customer_id: str):
    try:
        logging.info(f"Fetching notifications for customer {customer_id}.")
        subscriptions = await subscription_manager.get_customer_subscriptions(customer_id)
        notifications = []
        for sub in subscriptions:
            notification = await subscription_manager.get_notification(sub["subscription_id"])
            if notification:
                notifications.append(notification)
        logging.info(f"Found {len(notifications)} notifications for customer {customer_id}.")
        return {"notifications": notifications}
    except Exception as e:
        logging.error(f"Error in get_subscription_notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"message": "Welcome to CARE API"}

@app.get("/analytics")
async def get_analytics():
    try:
        logging.info("Fetching analytics data.")
        analytics = {
            "total_interactions": 127,
            "resolution_rate": 89.5,
            "avg_response_time": 1.2,
            "intent_distribution": {
                "WALLET_ISSUE": 35, "DELIVERY_ISSUE": 28, "PAYMENT_PROBLEM": 22, "ORDER_STATUS": 20,
                "REFUND_REQUEST": 15, "SUBSCRIPTION_REQUEST": 10, "GENERAL_INQUIRY": 7
            },
            "customer_satisfaction": 4.3,
            "top_issues": [
                "Wallet balance discrepancy", "Delivery delays", "Payment failures", "Order tracking", "Subscription setup"
            ]
        }
        logging.info("Analytics data sent.")
        return analytics
    except Exception as e:
        logging.error(f"Error in get_analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/validate")
async def validate_request(file: UploadFile = File(...), message: str = Form(""), customer_id: str = Form("WM001")):
    try:
        logging.info(f"Processing validation request for customer {customer_id} with file {file.filename}")
        contents = await file.read()
        case_id = str(uuid.uuid4())
        order_id = await resolution_agent._extract_order_id(message)  # Ensure this is async if needed
        refund_amount = await data_handler.get_order_amount(order_id) if order_id else 50.0
        validation_result = await resolution_agent.process_request(
            intent="REFUND_REQUEST",
            message=message,
            customer_id=customer_id,
            case_id=case_id,
            image_data=contents,
            refund_amount=refund_amount
        )
        ref_id = f"REF-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        response_data = {
            "status": validation_result.get("status", "escalated"),
            "message": validation_result.get("message", "Processing completed"),
            "category": "Refund Request",
            "priority": "Standard" if validation_result.get("status") == "resolved" else "High",
            "reference_id": ref_id,
            "validation_details": validation_result
        }
        logging.info(f"Validation response for customer {customer_id}: {response_data}")
        return response_data
    except Exception as e:
        logging.error(f"Error in validate_request: {e}")
        ref_id = f"REF-ERR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        return {
            "status": "escalated",
            "message": f"We apologize, but we encountered an issue processing your request: {str(e)}. Escalated for review.",
            "category": "Refund Request",
            "priority": "High",
            "reference_id": ref_id
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)