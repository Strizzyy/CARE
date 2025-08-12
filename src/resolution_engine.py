# resolution_engine.py
import base64
import uuid
import logging
import json
import re
from typing import Dict, Optional
from datetime import datetime
from data_handler import MongoDBHandler
import google.generativeai as genai
from langgraph.graph import StateGraph, END
from typing import TypedDict, Literal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("logs/resolution_engine.log"), logging.StreamHandler()]
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
    status: Literal["resolved", "escalated", "pending_image", "error"]
    response: str
    validation_result: Optional[Dict]

class ResolutionAgent:
    def __init__(self, data_handler: MongoDBHandler, gemini_api_key: str):
        self.data_handler = data_handler
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")
        self.workflow = self._build_workflow()
    
    def _extract_order_id(self, message: str) -> Optional[str]:
        order_pattern = r'ORD\d{3}'
        match = re.search(order_pattern, message)
        return match.group() if match else None
       
    async def _validate_refund_with_gemini(self, state: AgentState) -> Dict:
        """Validate refund request using Gemini API for image analysis"""
        logging.info(f"Validating refund request for customer {state['customer_id']}, order {state['order_id']}")
        
        # Check order status and payment status
        order = await self.data_handler.get_order(state['order_id'])
        payment = await self.data_handler.get_order_payment(state['order_id'])
        
        if not order:
            logging.warning(f"Order {state['order_id']} not found for customer {state['customer_id']}")
            return {
                "status": "escalated",
                "message": f"Order {state['order_id']} not found. Escalated for manual review.",
                "confidence": 0.0,
                "reason": "order_not_found"
            }
        
        if order.get("status") == "cancelled":
            logging.info(f"Order {state['order_id']} is cancelled")
            return {
                "status": "escalated",
                "message": f"Order {state['order_id']} is cancelled. No refund applicable.",
                "confidence": 0.0,
                "reason": "order_cancelled"
            }
        
        if payment and payment.get("status") == "refunded":
            logging.info(f"Order {state['order_id']} already refunded")
            return {
                "status": "escalated",
                "message": f"Order {state['order_id']} was already refunded on {payment.get('refund_date')}.",
                "confidence": 0.0,
                "reason": "already_refunded"
            }
        
        # Validate image data
        if not state['image_data'] or len(state['image_data']) == 0:
            logging.warning("No valid image data provided")
            return {
                "status": "escalated",
                "message": "No valid image data provided for validation.",
                "confidence": 0.0,
                "reason": "no_image"
            }
        
        try:
            img_base64 = base64.b64encode(state['image_data']).decode('utf-8')
            prompt = f"""
            You are an AI agent for validating refund requests based on images. Analyze the uploaded image carefully.
            
            Customer ID: {state['customer_id']}
            Order ID: {state['order_id']}
            Refund Amount: ₹{state['refund_amount']}
            Customer Message: {state['message']}
            
            INSTRUCTIONS:
            1. Examine the image for clear evidence of:
               - Visible damage (broken, cracked, spoiled)
               - Defective products (wrong color, size, missing parts)
               - Incorrect items (different from what was ordered)
            
            2. Decision criteria:
               - If damage/defect is CLEARLY visible and obvious → status: "resolved"
               - If image is unclear, blurry, or no obvious issue → status: "escalated"
               - If you cannot determine the issue → status: "escalated"
            
            3. Provide confidence score (0.0-1.0):
               - 0.8-1.0: Very clear damage/defect
               - 0.5-0.7: Some evidence but unclear
               - 0.0-0.4: No clear evidence or unclear image
            
            Return ONLY a valid JSON object:
            {{
                "status": "resolved" or "escalated",
                "message": "Brief explanation of decision",
                "confidence": 0.0-1.0,
                "reason": "damage_visible" or "unclear_image" or "no_issue_detected"
            }}
            """
            
            response = self.model.generate_content([
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": img_base64}}
            ])
            
            logging.info(f"Raw Gemini response: {response.text}")
            
            # Parse JSON response with better error handling
            try:
                # Clean the response text
                response_text = response.text.strip()
                if response_text.startswith("```json"):
                    response_text = response_text[7:-3].strip()
                elif response_text.startswith("```"):
                    response_text = response_text[3:-3].strip()
                
                result = json.loads(response_text)
                
                # Validate required fields
                if not all(key in result for key in ["status", "message", "confidence"]):
                    raise ValueError("Missing required fields in Gemini response")
                
                # Validate status value
                if result["status"] not in ["resolved", "escalated"]:
                    result["status"] = "escalated"
                
                # Validate confidence score
                confidence = float(result.get("confidence", 0.0))
                if confidence < 0.0 or confidence > 1.0:
                    confidence = 0.0
                result["confidence"] = confidence
                
                logging.info(f"Gemini validation result: {result}")
                
                # If resolved and high confidence, process refund
                if result["status"] == "resolved" and confidence >= 0.7:
                    customer = await self.data_handler.get_customer(state['customer_id'])
                    if customer:
                        new_balance = customer["wallet_balance"] + state['refund_amount']
                        await self.data_handler.update_wallet_balance(state['customer_id'], new_balance)
                        result["message"] = f"Refund of ₹{state['refund_amount']} processed successfully. New wallet balance: ₹{new_balance}"
                        logging.info(f"Refund processed for customer {state['customer_id']}, new balance: ₹{new_balance}")
                    else:
                        logging.warning(f"Customer {state['customer_id']} not found during refund processing")
                        result["status"] = "escalated"
                        result["message"] = "Customer not found during refund processing. Escalated for manual review."
                
                # If low confidence, escalate regardless of initial status
                elif confidence < 0.7:
                    result["status"] = "escalated"
                    result["message"] = f"Image analysis inconclusive (confidence: {confidence:.2f}). Escalated for human review."
                
                return result
                
            except (json.JSONDecodeError, ValueError) as e:
                logging.error(f"JSON parsing error in Gemini response: {e}")
                return {
                    "status": "escalated",
                    "message": "Unable to analyze image properly. Escalated for manual review.",
                    "confidence": 0.0,
                    "reason": "parsing_error"
                }
                
        except Exception as e:
            logging.error(f"Error validating refund with Gemini: {e}")
            return {
                "status": "escalated",
                "message": f"Technical error during validation: {str(e)}. Escalated for manual review.",
                "confidence": 0.0,
                "reason": "technical_error"
            }
       
    async def fetch_order_node(self, state: AgentState) -> AgentState:
        """Extract and validate order information"""
        logging.info(f"Fetching order info for intent: {state['intent']}")
        
        if state["intent"] == "REFUND_REQUEST":
            # Try to extract order ID from message
            state["order_id"] = self._extract_order_id(state["message"])
            
            # If no order ID found and we have image data, try to get the most recent order for the customer
            if not state["order_id"] and state.get("image_data"):
                logging.info("No order ID in message, but image provided. Trying to find recent orders for customer.")
                try:
                    customer_orders = await self.data_handler.get_customer_orders(state["customer_id"])
                    # Get the most recent delivered order (likely candidate for refund)
                    recent_orders = [order for order in customer_orders if order.get("status") == "delivered"]
                    if recent_orders:
                        # Sort by order_date and get the most recent
                        recent_orders.sort(key=lambda x: x.get("order_date", ""), reverse=True)
                        state["order_id"] = recent_orders[0]["order_id"]
                        logging.info(f"Inferred order ID from recent orders: {state['order_id']}")
                except Exception as e:
                    logging.error(f"Error getting customer orders: {e}")
            
            if state["order_id"]:
                try:
                    state["order_data"] = await self.data_handler.get_order(state["order_id"])
                    if not state["order_data"]:
                        state["status"] = "escalated"
                        state["response"] = f"Order {state['order_id']} not found. Escalated for manual review."
                        await self.data_handler.add_escalation(state["case_id"], state["customer_id"], 
                                                              f"Order not found: {state['message']}")
                    else:
                        # Set refund amount from order if not provided
                        if not state["refund_amount"]:
                            state["refund_amount"] = state["order_data"].get("total_amount", 0.0)
                        logging.info(f"Order {state['order_id']} found, refund amount: ₹{state['refund_amount']}")
                except Exception as e:
                    logging.error(f"Error fetching order {state['order_id']}: {e}")
                    state["status"] = "escalated"
                    state["response"] = f"Error retrieving order {state['order_id']}. Escalated for manual review."
                    await self.data_handler.add_escalation(state["case_id"], state["customer_id"], 
                                                          f"Error fetching order: {str(e)}. Message: {state['message']}")
            else:
                state["status"] = "escalated"
                state["response"] = "Please provide a valid order ID (e.g., ORD001) for your refund request."
                await self.data_handler.add_escalation(state["case_id"], state["customer_id"], 
                                                      f"No order ID provided: {state['message']}")
        
        return state
       
    async def refund_decision_node(self, state: AgentState) -> AgentState:
        """Make refund decision based on image analysis"""
        logging.info(f"Processing refund decision for order {state.get('order_id')}")
        
        if state["intent"] == "REFUND_REQUEST" and state.get("order_data"):
            if not state.get("image_data"):
                state["status"] = "pending_image"
                state["response"] = f"Please upload an image of the damaged item for order {state['order_id']} to process your refund."
                logging.info(f"Requesting image for order {state['order_id']}")
            else:
                try:
                    # Validate refund with Gemini
                    validation_result = await self._validate_refund_with_gemini(state)
                    state["validation_result"] = validation_result
                    state["status"] = validation_result["status"]
                    state["response"] = validation_result["message"]
                    
                    # If escalated, add to escalation queue
                    if validation_result["status"] == "escalated":
                        escalation_details = {
                            "customer_message": state["message"],
                            "order_id": state["order_id"],
                            "refund_amount": state["refund_amount"],
                            "validation_result": validation_result,
                            "image_provided": True
                        }
                        await self.data_handler.add_escalation(
                            state["case_id"], 
                            state["customer_id"], 
                            f"Refund validation escalated: {json.dumps(escalation_details)}"
                        )
                        logging.info(f"Refund request escalated for case {state['case_id']}")
                    
                except Exception as e:
                    logging.error(f"Error in refund validation: {e}")
                    state["status"] = "escalated"
                    state["response"] = f"Technical error during validation. Escalated for manual review."
                    await self.data_handler.add_escalation(
                        state["case_id"], 
                        state["customer_id"], 
                        f"Technical error: {str(e)}. Message: {state['message']}"
                    )
        
        elif state["intent"] == "REFUND_REQUEST" and not state.get("order_data"):
            # Order data not found, already handled in fetch_order_node
            pass
        
        return state
       
    async def handle_other_intents_node(self, state: AgentState) -> AgentState:
        """Handle non-refund intents"""
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
       
    def _should_process_refund(self, state: AgentState) -> str:
        """Determine next step for refund processing"""
        if state["intent"] != "REFUND_REQUEST":
            return "handle_other_intents"
        
        if state["status"] == "escalated":
            return "END"
        
        if not state.get("order_data"):
            return "END"
        
        return "refund_decision"
    
    def _build_workflow(self):
        """Build the LangGraph workflow for request processing"""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("fetch_order", self.fetch_order_node)
        workflow.add_node("refund_decision", self.refund_decision_node)
        workflow.add_node("handle_other_intents", self.handle_other_intents_node)
        
        # Add conditional edges
        workflow.add_conditional_edges(
            "fetch_order",
            self._should_process_refund,
            {
                "refund_decision": "refund_decision",
                "handle_other_intents": "handle_other_intents",
                "END": END
            }
        )
        
        # Add terminal edges
        workflow.add_edge("refund_decision", END)
        workflow.add_edge("handle_other_intents", END)
        
        # Set entry point
        workflow.set_entry_point("fetch_order")
        
        return workflow.compile()
       
    async def process_request(self, intent: str, message: str, customer_id: str, case_id: str, 
                            image_data: bytes = None, refund_amount: float = None) -> Dict:
        """Process customer request through the LangGraph workflow"""
        logging.info(f"Processing request for customer {customer_id}, intent: {intent}, case_id: {case_id}")
        
        # Initialize state
        initial_state = {
            "intent": intent,
            "message": message,
            "customer_id": customer_id,
            "case_id": case_id,
            "order_id": None,
            "order_data": None,
            "image_data": image_data,
            "refund_amount": refund_amount,
            "status": "pending",
            "response": "Processing your request...",
            "validation_result": None
        }
        
        try:
            # Execute workflow
            result = await self.workflow.ainvoke(initial_state)
            
            # Validate result
            if not result or "status" not in result or "response" not in result:
                logging.error(f"Invalid workflow result: {result}")
                raise ValueError("Workflow returned invalid state")
            
            # Prepare response
            response_data = {
                "status": result["status"],
                "message": result["response"],
                "case_id": result.get("case_id"),
                "order_id": result.get("order_id")
            }
            
            # Add validation details if available
            if result.get("validation_result"):
                response_data["validation_details"] = result["validation_result"]
            
            logging.info(f"Request processed successfully: {response_data['status']}")
            return response_data
            
        except Exception as e:
            logging.error(f"Error in workflow execution: {e}", exc_info=True)
            
            # Add to escalation queue
            await self.data_handler.add_escalation(
                case_id, 
                customer_id, 
                f"Workflow error: {str(e)}. Original message: {message}"
            )
            
            return {
                "status": "escalated",
                "message": "We encountered a technical issue processing your request. It has been escalated for manual review.",
                "case_id": case_id,
                "error": str(e)
            }