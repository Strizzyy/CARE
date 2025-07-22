import groq
import re
from typing import Dict, Tuple
from data_handler import MongoDBHandler
import asyncio

class NLUPipeline:
    def __init__(self, groq_api_key: str, mongodb_uri: str):
        self.client = groq.Groq(api_key=groq_api_key)
        self.data_handler = MongoDBHandler(mongodb_uri)
        self.intent_keywords = {
            'REFUND_REQUEST': ['refund', 'money back', 'return', 'cancel order', 'get my money', 'damaged'],
            'DELIVERY_ISSUE': ['not delivered', 'missing', 'delay', 'late', 'not received', 'where is'],
            'PAYMENT_PROBLEM': ['charged twice', 'payment failed', 'double charge', 'not charged', 'billing'],
            'WALLET_ISSUE': ['wallet', 'balance', 'credited', 'deducted', 'shows 0', 'wallet empty'],
            'ORDER_STATUS': ['order status', 'tracking', 'shipped', 'when will', 'delivery date'],
            'SUBSCRIPTION_REQUEST': ['subscription', 'weekly delivery', 'recurring order', 'restock weekly', 'auto delivery'],
            'GENERAL_INQUIRY': ['help', 'support', 'question', 'how to', 'what is']
        }
    
    def extract_order_id(self, message: str) -> str:
        order_pattern = r'ORD\d{3}'
        match = re.search(order_pattern, message)
        return match.group() if match else None
    
    def extract_amount(self, message: str) -> float:
        amount_pattern = r'₹(\d+(?:\.\d{2})?)'
        match = re.search(amount_pattern, message)
        return float(match.group(1)) if match else None
    
    def extract_subscription_items(self, message: str) -> list[str]:
        words = message.lower().split()
        common_items = ['milk', 'vegetables', 'rice', 'oil', 'detergent', 'biscuits']
        return [word for word in words if word in common_items]
    
    def classify_intent_quick(self, message: str) -> str:
        message_lower = message.lower()
        scores = {intent: sum(1 for keyword in keywords if keyword in message_lower) for intent, keywords in self.intent_keywords.items()}
        return max(scores.items(), key=lambda x: x[1])[0] if any(scores.values()) else 'GENERAL_INQUIRY'
    
    def classify_intent_groq(self, message: str) -> str:
        prompt = f"""
        Classify this customer support message into ONE of these intents:
        REFUND_REQUEST, DELIVERY_ISSUE, PAYMENT_PROBLEM, WALLET_ISSUE, ORDER_STATUS, SUBSCRIPTION_REQUEST, GENERAL_INQUIRY
        
        Message: "{message}"
        
        Return only the intent name, nothing else.
        """
        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Groq API error: {e}")
            return self.classify_intent_quick(message)
    
    def classify_intent(self, message: str) -> str:
        intent = self.classify_intent_quick(message)
        if intent == 'GENERAL_INQUIRY':
            intent = self.classify_intent_groq(message)
        return intent
    
    async def generate_response(self, intent: str, message: str, customer_id: str) -> str:
        customer = await self.data_handler.get_customer(customer_id)
        if not customer:
            return "I'm sorry, I couldn't find your customer information. Please contact support."
        
        order_id = self.extract_order_id(message)
        amount = self.extract_amount(message)
        context = f"""
        You are a helpful customer support agent for CARE. Respond professionally and helpfully.
        
        Customer Information:
        - Name: {customer['name']}
        - Wallet Balance: ₹{customer['wallet_balance']}
        - Membership: {customer['membership']}
        - Location: {customer['location']}
        
        Recent Orders: {len(await self.data_handler.get_customer_orders(customer_id))} orders
        Active Subscriptions: {len([s for s in await self.data_handler.get_customer_subscriptions(customer_id) if s['status'] == 'active'])} subscriptions
        Intent: {intent}
        Customer Message: "{message}"
        """
        
        if intent == 'WALLET_ISSUE':
            context += "Recent payments: {} transactions\nCurrent wallet balance: ₹{}\nIf wallet shows ₹0 but customer paid, explain payment processing and offer to credit wallet.".format(
                len(await self.data_handler.get_customer_payments(customer_id)), customer['wallet_balance'])
        
        elif intent == 'DELIVERY_ISSUE':
            if order_id:
                order = await self.data_handler.get_order(order_id)
                if order:
                    context += f"\nOrder {order_id} details:\n- Status: {order['status']}\n- Expected delivery: {order['expected_delivery']}\n- Items: {len(order['items'])} items"
        
        elif intent == 'PAYMENT_PROBLEM':
            failed_payments = await self.data_handler.get_failed_payments(customer_id)
            context += f"\nFailed payments: {len(failed_payments)}\nRecent payment issues found."
        
        elif intent == 'REFUND_REQUEST':
            context += "\nFor refunds, suggest uploading an image of the damaged item or proof. If evidence is provided, validate and process autonomously or escalate."
        
        elif intent == 'SUBSCRIPTION_REQUEST':
            items = self.extract_subscription_items(message)
            context += f"\nCustomer wants to set up a subscription.\nPotential items mentioned: {', '.join(items) if items else 'None'}\nSuggest creating a subscription for these items with weekly delivery or ask for clarification."
        
        context += "\n\nProvide a concise, helpful response (max 100 words)."
        
        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": context}],
                max_tokens=150
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Response generation error: {e}")
            return self._fallback_response(intent, customer, order_id)
    
    def _fallback_response(self, intent: str, customer: Dict, order_id: str = None) -> str:
        responses = {
            'WALLET_ISSUE': f"Hi {customer['name']}! Your wallet balance is ₹{customer['wallet_balance']}. Let me resolve this.",
            'DELIVERY_ISSUE': f"Hi {customer['name']}! Checking delivery status for {order_id if order_id else 'your order'}.",
            'PAYMENT_PROBLEM': f"Hi {customer['name']}! Reviewing your payment issues.",
            'ORDER_STATUS': f"Hi {customer['name']}! Checking order status.",
            'REFUND_REQUEST': f"Hi {customer['name']}! Please upload an image of the damaged item for refund processing.",
            'SUBSCRIPTION_REQUEST': f"Hi {customer['name']}! Let’s set up a subscription. Specify items and day.",
            'GENERAL_INQUIRY': f"Hi {customer['name']}! How can I assist you?"
        }
        return responses.get(intent, "I'm here to help you with your query!")