# resolution_engine.py
import base64
import uuid
import logging
from typing import Dict, Optional
from datetime import datetime
from data_handler import MongoDBHandler
import google.generativeai as genai
from langgraph.graph import StateGraph, END
from typing import TypedDict, Literal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("resolution_engine.log"), logging.StreamHandler()]
)

class AgentState(TypedDict):
    intent: str
    message: str
    customer_id: str
    case_id: str
    order_id: Optional[str]
    order_data: Optional[Dict]
    image_data: Optional[bytes]
    refund_amount: Optional[float]
    status: Literal["resolved", "escalated", "pending_image"]
    response: str
    case_id: Optional[str]

class ResolutionAgent:
       def __init__(self, data_handler: MongoDBHandler, gemini_api_key: str):
           self.data_handler = data_handler
           genai.configure(api_key=gemini_api_key)
           self.model = genai.GenerativeModel("gemini-1.5-flash")
           self.workflow = self._build_workflow()
       
       def _extract_order_id(self, message: str) -> Optional[str]:
           import re
           order_pattern = r'ORD\d{3}'
           match = re.search(order_pattern, message)
           return match.group() if match else None
       
       async def _validate_refund_with_gemini(self, state: AgentState) -> Dict:
           logging.info(f"Validating refund request for customer {state['customer_id']}, order {state['order_id']}")
           
           # Check order status and payment status
           order = await self.data_handler.get_order(state['order_id'])
           payment = await self.data_handler.get_order_payment(state['order_id'])
           if not order:
               logging.warning(f"Order {state['order_id']} not found for customer {state['customer_id']}")
               return {
                   "status": "escalated",
                   "message": f"Order {state['order_id']} not found. Escalated for manual review.",
                   "case_id": state['case_id']
               }
           if order.get("status") == "cancelled":
               logging.info(f"Order {state['order_id']} is cancelled")
               return {
                   "status": "escalated",
                   "message": f"Order {state['order_id']} is cancelled. No refund applicable.",
                   "case_id": state['case_id']
               }
           if payment and payment.get("status") == "refunded":
               logging.info(f"Order {state['order_id']} already refunded")
               return {
                   "status": "escalated",
                   "message": f"Order {state['order_id']} was already refunded on {payment.get('refund_date')}.",
                   "case_id": state['case_id']
               }
           
           # Validate image data
           if not state['image_data'] or len(state['image_data']) == 0:
               logging.warning("No valid image data provided")
               return {
                   "status": "escalated",
                   "message": "No valid image data provided for validation.",
                   "case_id": state['case_id']
               }
           
           try:
               img_base64 = base64.b64encode(state['image_data']).decode('utf-8')
               prompt = f"""
               You are an AI agent for validating refund requests based on images.
               Customer ID: {state['customer_id']}
               Order ID: {state['order_id']}
               Refund Amount Requested: ₹{state['refund_amount']}
               Customer Message: {state['message']}
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
               logging.info(f"Raw Gemini response: {response.text}")
               # Safely parse JSON response
               import json
               result = json.loads(response.text.strip()) if response.text and response.text.strip() else {
                   "status": "escalated",
                   "message": "Invalid or empty response from Gemini API.",
                   "case_id": state['case_id']
               }
               logging.info(f"Gemini validation result: {result}")
               
               if result["status"] == "resolved":
                   customer = await self.data_handler.get_customer(state['customer_id'])
                   if customer:
                       new_balance = customer["wallet_balance"] + state['refund_amount']
                       await self.data_handler.update_wallet_balance(state['customer_id'], new_balance)
                       logging.info(f"Refund of ₹{state['refund_amount']} processed for customer {state['customer_id']}, new wallet balance: ₹{new_balance}")
                   else:
                       logging.warning(f"Customer {state['customer_id']} not found during refund processing")
                       result["status"] = "escalated"
                       result["message"] = "Customer not found during refund processing. Escalated for manual review."
               return result
           except json.JSONDecodeError as e:
               logging.error(f"JSON parsing error in Gemini response: {e}")
               await self.data_handler.add_escalation(state['case_id'], state['customer_id'], f"JSON parsing error: {str(e)}. Message: {state['message']}")
               return {
                   "status": "escalated",
                   "message": f"Failed to parse Gemini response: {str(e)}. Escalated for manual review.",
                   "case_id": state['case_id']
               }
           except Exception as e:
               logging.error(f"Error validating refund: {e}")
               await self.data_handler.add_escalation(state['case_id'], state['customer_id'], f"Error: {str(e)}. Message: {state['message']}")
               return {
                   "status": "escalated",
                   "message": f"Failed to validate refund request: {str(e)}. Escalated for manual review.",
                   "case_id": state['case_id']
               }
       
       async def fetch_order_node(self, state: AgentState) -> AgentState:
           if state["intent"] == "REFUND_REQUEST":
               state["order_id"] = self._extract_order_id(state["message"])
               if state["order_id"]:
                   state["order_data"] = await self.data_handler.get_order(state["order_id"])
                   if not state["order_data"]:
                       state["status"] = "escalated"
                       state["response"] = f"Order {state['order_id']} not found. Escalated for manual review."
                       await self.data_handler.add_escalation(state["case_id"], state["customer_id"], state["message"])
               else:
                   state["status"] = "escalated"
                   state["response"] = "Please provide a valid order ID (e.g., ORD001) for your refund request."
                   await self.data_handler.add_escalation(state["case_id"], state["customer_id"], state["message"])
           return state
       
       async def refund_decision_node(self, state: AgentState) -> AgentState:
           if state["intent"] == "REFUND_REQUEST" and state["order_data"]:
               if not state["image_data"]:
                   state["status"] = "pending_image"
                   state["response"] = f"Please upload an image of the damaged item for order {state['order_id']} to process your refund."
               else:
                   try:
                       result = await self._validate_refund_with_gemini(state)
                       state["status"] = result["status"]
                       state["response"] = result["message"]
                       if "case_id" in result:
                           state["case_id"] = result["case_id"]
                   except Exception as e:
                       logging.error(f"Error in refund validation: {e}")
                       state["status"] = "escalated"
                       state["response"] = f"Failed to validate refund request: {str(e)}. Escalated for manual review."
                       await self.data_handler.add_escalation(state["case_id"], state["customer_id"], f"Error: {str(e)}. Message: {state['message']}")
           return state
       
       async def handle_other_intents_node(self, state: AgentState) -> AgentState:
           if state["intent"] != "REFUND_REQUEST":
               customer = await self.data_handler.get_customer(state["customer_id"])
               if not customer:
                   state["status"] = "error"
                   state["response"] = "Customer not found."
                   return state
               
               if state["intent"] == "WALLET_ISSUE":
                   failed_payments = await self.data_handler.get_failed_payments(state["customer_id"])
                   if failed_payments:
                       state["status"] = "escalated"
                       state["response"] = "We've detected payment issues. Escalated for review."
                       await self.data_handler.add_escalation(state["case_id"], state["customer_id"], state["message"])
                   else:
                       state["status"] = "resolved"
                       state["response"] = f"Your wallet balance is ₹{customer['wallet_balance']}. No issues detected."
               
               elif state["intent"] == "DELIVERY_ISSUE":
                   order_id = self._extract_order_id(state["message"])
                   if order_id:
                       order = await self.data_handler.get_order(order_id)
                       if order:
                           state["status"] = "resolved"
                           state["response"] = f"Order {order_id} status: {order['status']}. Expected delivery: {order['expected_delivery']}."
                       else:
                           state["status"] = "escalated"
                           state["response"] = "Unable to track delivery. Escalated for manual review."
                           await self.data_handler.add_escalation(state["case_id"], state["customer_id"], state["message"])
               
               elif state["intent"] == "PAYMENT_PROBLEM":
                   failed_payments = await self.data_handler.get_failed_payments(state["customer_id"])
                   if failed_payments:
                       state["status"] = "escalated"
                       state["response"] = f"Found {len(failed_payments)} failed payment(s). Escalated for review."
                       await self.data_handler.add_escalation(state["case_id"], state["customer_id"], state["message"])
                   else:
                       state["status"] = "resolved"
                       state["response"] = "No payment issues found."
               
               elif state["intent"] == "ORDER_STATUS":
                   order_id = self._extract_order_id(state["message"])
                   if order_id:
                       order = await self.data_handler.get_order(order_id)
                       if order:
                           state["status"] = "resolved"
                           state["response"] = f"Order {order_id} status: {order['status']}. Expected delivery: {order['expected_delivery']}."
                       else:
                           state["status"] = "escalated"
                           state["response"] = "Order not found. Please provide a valid order ID."
                           await self.data_handler.add_escalation(state["case_id"], state["customer_id"], state["message"])
               
               else:
                   state["status"] = "escalated"
                   state["response"] = "Unable to process your request automatically. Escalated for manual review."
                   await self.data_handler.add_escalation(state["case_id"], state["customer_id"], state["message"])
           return state
       
       def _build_workflow(self):
           workflow = StateGraph(AgentState)
           workflow.add_node("fetch_order", self.fetch_order_node)
           workflow.add_node("refund_decision", self.refund_decision_node)
           workflow.add_node("handle_other_intents", self.handle_other_intents_node)
           
           workflow.add_conditional_edges(
               "fetch_order",
               lambda state: "refund_decision" if state["intent"] == "REFUND_REQUEST" else "handle_other_intents",
               {
                   "refund_decision": "refund_decision",
                   "handle_other_intents": "handle_other_intents"
               }
           )
           workflow.add_edge("refund_decision", END)
           workflow.add_edge("handle_other_intents", END)
           
           workflow.set_entry_point("fetch_order")
           return workflow.compile()
       
       async def process_request(self, intent: str, message: str, customer_id: str, case_id: str, image_data: bytes = None, refund_amount: float = None) -> Dict:
           logging.info(f"Processing request for customer {customer_id}, intent: {intent}, case_id: {case_id}")
           
           state = {
               "intent": intent,
               "message": message,
               "customer_id": customer_id,
               "case_id": case_id,
               "order_id": None,
               "order_data": None,
               "image_data": image_data,
               "refund_amount": refund_amount,
               "status": "pending",
               "response": "Processing your request..."
           }
           
           try:
               result = await self.workflow.ainvoke(state)
               if not result or "status" not in result or "response" not in result:
                   logging.error(f"Invalid workflow result: {result}")
                   raise ValueError("Workflow returned invalid state")
               return {
                   "status": result["status"],
                   "message": result["response"],
                   "case_id": result["case_id"] if result.get("case_id") else None
               }
           except Exception as e:
               logging.error(f"Error in workflow execution: {e}")
               await self.data_handler.add_escalation(case_id, customer_id, f"Error: {str(e)}. Message: {message}")
               return {
                   "status": "escalated",
                   "message": f"Failed to process request: {str(e)}. Escalated for manual review.",
                   "case_id": case_id
               }