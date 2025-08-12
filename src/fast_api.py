# fast_api.py
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
import re
import logging
import os

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("logs/care_api.log"), logging.StreamHandler()]
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
    nlu = NLUPipeline(GROQ_API_KEY, data_handler)
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
        
        # Verify customer exists
        customer = await data_handler.get_customer(customer_id)
        if not customer:
            case_id = str(uuid.uuid4())
            await data_handler.add_escalation(case_id, customer_id, f"Customer not found. Message: {message}")
            return {
                "response": f"Customer ID {customer_id} not found. Please verify your customer ID.",
                "intent": "ERROR",
                "status": "escalated",
                "case_id": case_id
            }
        
        # Classify intent using NLUPipeline
        intent = await nlu.classify_intent(message)
        logging.info(f"Detected intent: {intent}")
        
        # Generate case ID for tracking
        case_id = str(uuid.uuid4())
        
        # Process request through LangGraph agent
        agent_result = await resolution_agent.process_request(
            intent=intent,
            message=message,
            customer_id=customer_id,
            case_id=case_id
        )
        
        # Return agent result
        return {
            "response": agent_result["message"],
            "intent": intent,
            "status": agent_result["status"],
            "case_id": agent_result.get("case_id"),
            "order_id": agent_result.get("order_id")
        }
        
    except Exception as e:
        logging.error(f"Error in chat_endpoint for customer {customer_id}: {str(e)}", exc_info=True)
        case_id = str(uuid.uuid4())
        await data_handler.add_escalation(case_id, customer_id, f"Error: {str(e)}. Message: {message}")
        return {
            "response": "I apologize, but I encountered an error. Your request has been escalated for review.",
            "intent": "ERROR",
            "status": "escalated",
            "case_id": case_id
        }


@app.post("/subscription")
async def create_subscription(request: SubscriptionRequest):
    try:
        logging.info(f"Creating subscription for customer {request.customer_id}")
        subscription_id = f"SUB{str(uuid.uuid4())[:8].upper()}"
        subscription = {
            "subscription_id": subscription_id,
            "customer_id": request.customer_id,
            "items": request.items,
            "delivery_date": request.delivery_date,
            "subscription_type": request.subscription_type,
            "status": "active",
            "created_at": datetime.now().isoformat()
        }
        await subscription_manager.create_subscription(subscription)
        logging.info(f"Subscription {subscription_id} created for customer {request.customer_id}")
        return {"message": f"Subscription {subscription_id} created successfully", "subscription_id": subscription_id}
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

@app.get("/escalations/all")
async def get_all_escalations():
    try:
        logging.info("Fetching all escalations for human agent dashboard")
        escalations = await data_handler.get_all_escalations()
        return {"escalations": escalations}
    except Exception as e:
        logging.error(f"Error in get_all_escalations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/escalations/{customer_id}")
async def get_customer_escalations(customer_id: str):
    try:
        logging.info(f"Fetching escalations for customer {customer_id}")
        escalations = await data_handler.get_customer_escalations(customer_id)
        return {"escalations": escalations}
    except Exception as e:
        logging.error(f"Error in get_customer_escalations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/escalation/{case_id}")
async def get_escalation_status(case_id: str):
    try:
        logging.info(f"Fetching escalation status for case {case_id}")
        escalation = await data_handler.get_escalation(case_id)
        if not escalation:
            raise HTTPException(status_code=404, detail="Escalation case not found")
        return {"escalation": escalation}
    except Exception as e:
        logging.error(f"Error in get_escalation_status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/escalation/{case_id}/resolve")
async def resolve_escalation(case_id: str, resolution: dict):
    try:
        logging.info(f"Resolving escalation case {case_id} with resolution: {resolution}")
        
        # Update escalation status with resolution details
        success = await data_handler.resolve_escalation(case_id, resolution)
        if not success:
            raise HTTPException(status_code=404, detail="Escalation case not found")
        
        # If it's an approved refund, process the refund
        if resolution.get("resolution_type") == "approved" and resolution.get("refund_amount"):
            escalation = await data_handler.get_escalation(case_id)
            if escalation:
                customer_id = escalation.get("customer_id")
                refund_amount = float(resolution.get("refund_amount", 0))
                
                # Process refund by updating wallet balance
                customer = await data_handler.get_customer(customer_id)
                if customer:
                    new_balance = customer["wallet_balance"] + refund_amount
                    await data_handler.update_wallet_balance(customer_id, new_balance)
                    logging.info(f"Refund of ₹{refund_amount} processed for customer {customer_id} by human agent")
        
        return {"message": f"Escalation case {case_id} resolved", "resolution": resolution}
    except Exception as e:
        logging.error(f"Error in resolve_escalation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
        
        # Verify customer exists
        customer = await data_handler.get_customer(customer_id)
        if not customer:
            case_id = str(uuid.uuid4())
            await data_handler.add_escalation(case_id, customer_id, f"Customer not found. Message: {message}")
            return {
                "status": "escalated",
                "message": f"Customer ID {customer_id} not found. Escalated for manual review.",
                "category": "Refund Request",
                "priority": "High",
                "reference_id": f"REF-ERR-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "case_id": case_id
            }
        
        # Read file contents
        contents = await file.read()
        if not contents:
            return {
                "status": "escalated",
                "message": "No valid image data received. Please upload a clear image of the damaged item.",
                "category": "Refund Request",
                "priority": "High",
                "reference_id": f"REF-ERR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            }
        
        # Generate case ID and extract order info
        case_id = str(uuid.uuid4())
        order_id = resolution_agent._extract_order_id(message)
        
        # If no order ID found in message, provide a default message that includes context
        if not order_id and message in ["Image uploaded", "Refund request with image", ""]:
            message = "Refund request with image - please process based on uploaded evidence"
        
        refund_amount = await data_handler.get_order_amount(order_id) if order_id else None
        
        # Process through LangGraph agent
        validation_result = await resolution_agent.process_request(
            intent="REFUND_REQUEST",
            message=message,
            customer_id=customer_id,
            case_id=case_id,
            image_data=contents,
            refund_amount=refund_amount
        )
        
        # Generate reference ID
        ref_id = f"REF-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Prepare response
        response_data = {
            "status": validation_result.get("status", "escalated"),
            "message": validation_result.get("message", "Processing completed"),
            "category": "Refund Request",
            "priority": "Standard" if validation_result.get("status") == "resolved" else "High",
            "reference_id": ref_id,
            "case_id": validation_result.get("case_id"),
            "order_id": validation_result.get("order_id")
        }
        
        # Add validation details if available
        if validation_result.get("validation_details"):
            response_data["validation_details"] = validation_result["validation_details"]
        
        logging.info(f"Validation response for customer {customer_id}: {response_data['status']}")
        return response_data
        
    except Exception as e:
        logging.error(f"Error in validate_request: {e}", exc_info=True)
        ref_id = f"REF-ERR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        case_id = str(uuid.uuid4())
        await data_handler.add_escalation(case_id, customer_id, f"Validation error: {str(e)}. Message: {message}")
        return {
            "status": "escalated",
            "message": "We encountered a technical issue processing your request. It has been escalated for manual review.",
            "category": "Refund Request",
            "priority": "High",
            "reference_id": ref_id,
            "case_id": case_id
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)