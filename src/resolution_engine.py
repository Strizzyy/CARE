import base64
import uuid
import logging
from typing import Dict, Optional
from datetime import datetime
from data_handler import MongoDBHandler
import google.generativeai as genai

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("resolution_engine.log"), logging.StreamHandler()]
)

class ResolutionAgent:
    def __init__(self, data_handler: MongoDBHandler, gemini_api_key: str):
        self.data_handler = data_handler
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")
    
    def _extract_order_id(self, message: str) -> Optional[str]:
        import re
        order_pattern = r'ORD\d{3}'
        match = re.search(order_pattern, message)
        return match.group() if match else None
    
    async def _validate_refund_with_gemini(self, message: str, customer_id: str, image_data: bytes, order_id: str, refund_amount: float) -> Dict:
        logging.info(f"Validating refund request for customer {customer_id}, order {order_id}")
        
        # Check order status and payment status
        order = await self.data_handler.get_order(order_id)
        payment = await self.data_handler.get_order_payment(order_id)
        if not order:
            logging.warning(f"Order {order_id} not found for customer {customer_id}")
            return {
                "status": "escalated",
                "message": f"Order {order_id} not found. Escalated for manual review.",
                "case_id": str(uuid.uuid4())
            }
        if order.get("status") == "cancelled":
            logging.info(f"Order {order_id} is cancelled")
            return {
                "status": "escalated",
                "message": f"Order {order_id} is cancelled. No refund applicable.",
                "case_id": str(uuid.uuid4())
            }
        if payment and payment.get("status") == "refunded":
            logging.info(f"Order {order_id} already refunded")
            return {
                "status": "escalated",
                "message": f"Order {order_id} was already refunded on {payment.get('refund_date')}.",
                "case_id": str(uuid.uuid4())
            }
        
        # Proceed with image validation
        try:
            img_base64 = base64.b64encode(image_data).decode('utf-8')
            prompt = f"""
            You are an AI agent for validating refund requests based on images.
            Customer ID: {customer_id}
            Order ID: {order_id}
            Refund Amount Requested: ₹{refund_amount}
            Customer Message: {message}
            Instructions:
            - Analyze the image for evidence of damage, defect, or incorrect item.
            - If the issue is clear (e.g., visible damage), approve the refund.
            - If the image is unclear or missing evidence, escalate the request.
            - Return a JSON object with:
              - status: "resolved" or "escalated"
              - message: Explanation of the decision
              - case_id: UUID for tracking (only if escalated)
            """
            response = self.model.generate_content([
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": img_base64}}
            ])
            result = eval(response.text.strip())  # Assuming response is valid JSON
            logging.info(f"Gemini validation result: {result}")
            
            if result["status"] == "resolved":
                customer = await self.data_handler.get_customer(customer_id)
                new_balance = customer["wallet_balance"] + refund_amount
                await self.data_handler.update_wallet_balance(customer_id, new_balance)
                logging.info(f"Refund of ₹{refund_amount} processed for customer {customer_id}, new wallet balance: ₹{new_balance}")
                return result
            else:
                case_id = str(uuid.uuid4())
                await self.data_handler.add_escalation(case_id, customer_id, message)
                result["case_id"] = case_id
                logging.info(f"Refund request escalated, case ID: {case_id}")
                return result
        except Exception as e:
            logging.error(f"Error validating refund: {e}")
            case_id = str(uuid.uuid4())
            await self.data_handler.add_escalation(case_id, customer_id, f"Error: {str(e)}. Message: {message}")
            return {
                "status": "escalated",
                "message": f"Failed to validate refund request: {str(e)}. Escalated for manual review.",
                "case_id": case_id
            }
    
    async def process_request(self, intent: str, message: str, customer_id: str, case_id: str, image_data: bytes = None, refund_amount: float = None) -> Dict:
        logging.info(f"Processing request for customer {customer_id}, intent: {intent}, case_id: {case_id}")
        
        if intent == "REFUND_REQUEST":
            order_id = self._extract_order_id(message)
            if not order_id:
                logging.warning(f"No order ID found in message: {message}")
                await self.data_handler.add_escalation(case_id, customer_id, message)
                return {
                    "status": "escalated",
                    "message": "No order ID found in your request. Please provide a valid order ID.",
                    "case_id": case_id
                }
            if not refund_amount:
                refund_amount = await self.data_handler.get_order_amount(order_id)
                if not refund_amount:
                    logging.warning(f"No amount found for order {order_id}")
                    await self.data_handler.add_escalation(case_id, customer_id, message)
                    return {
                        "status": "escalated",
                        "message": f"No amount found for order {order_id}. Escalated for manual review.",
                        "case_id": case_id
                    }
            if not image_data:
                logging.warning(f"No image provided for refund request, order {order_id}")
                await self.data_handler.add_escalation(case_id, customer_id, message)
                return {
                    "status": "escalated",
                    "message": "Please upload an image of the damaged item to process your refund.",
                    "case_id": case_id
                }
            return await self._validate_refund_with_gemini(message, customer_id, image_data, order_id, refund_amount)
        
        # Handle other intents
        customer = await self.data_handler.get_customer(customer_id)
        if not customer:
            logging.error(f"Customer {customer_id} not found")
            return {"status": "error", "message": "Customer not found"}
        
        if intent == "WALLET_ISSUE":
            failed_payments = await self.data_handler.get_failed_payments(customer_id)
            if failed_payments:
                await self.data_handler.add_escalation(case_id, customer_id, message)
                return {
                    "status": "escalated",
                    "message": "We've detected payment issues. Escalated for review.",
                    "case_id": case_id
                }
            return {
                "status": "resolved",
                "message": f"Your wallet balance is ₹{customer['wallet_balance']}. No issues detected."
            }
        
        elif intent == "DELIVERY_ISSUE":
            order_id = self._extract_order_id(message)
            if order_id:
                order = await self.data_handler.get_order(order_id)
                if order:
                    return {
                        "status": "resolved",
                        "message": f"Order {order_id} status: {order['status']}. Expected delivery: {order['expected_delivery']}."
                    }
            await self.data_handler.add_escalation(case_id, customer_id, message)
            return {
                "status": "escalated",
                "message": "Unable to track delivery. Escalated for manual review.",
                "case_id": case_id
            }
        
        elif intent == "PAYMENT_PROBLEM":
            failed_payments = await self.data_handler.get_failed_payments(customer_id)
            if failed_payments:
                await self.data_handler.add_escalation(case_id, customer_id, message)
                return {
                    "status": "escalated",
                    "message": f"Found {len(failed_payments)} failed payment(s). Escalated for review.",
                    "case_id": case_id
                }
            return {
                "status": "resolved",
                "message": "No payment issues found."
            }
        
        elif intent == "ORDER_STATUS":
            order_id = self._extract_order_id(message)
            if order_id:
                order = await self.data_handler.get_order(order_id)
                if order:
                    return {
                        "status": "resolved",
                        "message": f"Order {order_id} status: {order['status']}. Expected delivery: {order['expected_delivery']}."
                    }
            return {
                "status": "escalated",
                "message": "Order not found. Please provide a valid order ID.",
                "case_id": case_id
            }
        
        else:
            return {
                "status": "escalated",
                "message": "Unable to process your request automatically. Escalated for manual review.",
                "case_id": case_id
            }