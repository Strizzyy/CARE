#!/usr/bin/env python3
"""
CARE: Customer Assistance Resolution Engine
Simplified Streamlit App for Deployment
"""
import streamlit as st
import requests
import json
import time
import os
import threading
import sys
from datetime import datetime
from PIL import Image
from io import BytesIO
import plotly.express as px
import logging

# Add src to path
sys.path.append('src')

# Configure logging
logging.basicConfig(level=logging.INFO)

# Page configuration
st.set_page_config(
    page_title="CARE: Customer Assistance Resolution Engine",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Environment setup
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:7860")

# Custom CSS
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #0078d4 0%, #005a9e 100%);
        color: white;
        padding: 2rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        text-align: center;
    }
    .customer-info {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 12px;
        border-left: 6px solid #0078d4;
        margin-bottom: 1.5rem;
    }
    .escalation-card {
        background: #fff3cd;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #ffc107;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "selected_customer" not in st.session_state:
    st.session_state.selected_customer = None
if "backend_started" not in st.session_state:
    st.session_state.backend_started = False

def start_backend():
    """Start FastAPI backend if not running"""
    if st.session_state.backend_started:
        return True
        
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=2)
        if response.status_code == 200:
            st.session_state.backend_started = True
            return True
    except:
        pass
    
    # Start backend in background
    try:
        import uvicorn
        from fast_api import app
        
        def run_server():
            uvicorn.run(app, host="0.0.0.0", port=7860, log_level="error")
        
        backend_thread = threading.Thread(target=run_server, daemon=True)
        backend_thread.start()
        time.sleep(5)  # Wait for server to start
        st.session_state.backend_started = True
        return True
    except Exception as e:
        st.error(f"Failed to start backend: {e}")
        return False

def get_customers():
    """Fetch customers from API"""
    try:
        response = requests.get(f"{API_BASE_URL}/customers", timeout=10)
        if response.status_code == 200:
            return response.json().get('customers', [])
        return []
    except Exception as e:
        st.error(f"Error fetching customers: {e}")
        return []

def get_customer_info(customer_id):
    """Fetch customer information"""
    try:
        response = requests.get(f"{API_BASE_URL}/customer/{customer_id}", timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        st.error(f"Error fetching customer info: {e}")
        return None

def send_message(message, customer_id, file=None):
    """Send message to chat API"""
    try:
        if file:
            files = {'file': (file.name, file.getvalue(), 'image/jpeg')}
            data = {'message': message or "Refund request with image", 'customer_id': customer_id}
            response = requests.post(f"{API_BASE_URL}/validate", files=files, data=data, timeout=30)
        else:
            response = requests.post(f"{API_BASE_URL}/chat", 
                                   json={"message": message, "customer_id": customer_id}, 
                                   timeout=10)
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"API Error: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Error sending message: {e}")
        return None

def get_escalations():
    """Get all escalated cases"""
    try:
        response = requests.get(f"{API_BASE_URL}/escalations/all", timeout=10)
        if response.status_code == 200:
            return response.json().get('escalations', [])
        return []
    except Exception as e:
        st.error(f"Error fetching escalations: {e}")
        return []

def resolve_escalation(case_id, resolution_type, notes):
    """Resolve an escalated case"""
    try:
        resolution_data = {
            "resolution_type": resolution_type,
            "notes": notes,
            "resolved_by": "Human Agent",
            "resolved_at": datetime.now().isoformat()
        }
        response = requests.post(f"{API_BASE_URL}/escalation/{case_id}/resolve", 
                               json=resolution_data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error resolving case: {e}")
        return False

def customer_support_page():
    """Main customer support interface"""
    st.markdown("""
    <div class="main-header">
        <h1>🛒 CARE: Customer Assistance Resolution Engine</h1>
        <p>AI-powered customer support with intelligent resolution</p>
    </div>
    """, unsafe_allow_html=True)

    # Sidebar for customer selection
    with st.sidebar:
        st.header("👤 Customer Selection")
        customers = get_customers()
        
        if customers:
            customer_options = {f"{c['name']} ({c['customer_id']})": c['customer_id'] for c in customers}
            selected_customer = st.selectbox(
                "Select Customer",
                options=list(customer_options.keys()),
                index=0 if customer_options else None
            )
            customer_id = customer_options.get(selected_customer)
            
            if customer_id != st.session_state.selected_customer:
                st.session_state.selected_customer = customer_id
                st.session_state.messages = []
        else:
            st.warning("No customers available. Starting backend...")
            customer_id = None

        # Quick scenarios
        if customer_id:
            st.header("🚀 Quick Scenarios")
            scenarios = [
                "I want a refund for order ORD001",
                "Where is my order ORD002?",
                "My payment failed",
                "My wallet balance shows ₹0"
            ]
            for scenario in scenarios:
                if st.button(scenario, key=f"scenario_{scenario}"):
                    response = send_message(scenario, customer_id)
                    if response:
                        st.session_state.messages.append({
                            "role": "user",
                            "content": scenario,
                            "timestamp": datetime.now().isoformat()
                        })
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": response.get('response', 'Processing...'),
                            "intent": response.get('intent', 'None'),
                            "status": response.get('status', 'Processing'),
                            "timestamp": datetime.now().isoformat()
                        })
                        st.rerun()

    # Main content
    col1, col2 = st.columns([2, 1])

    with col1:
        st.header("💬 Chat Support")
        
        if not customer_id:
            st.info("Please select a customer to start chatting.")
        else:
            # Display chat history
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.write(message["content"])
                    if message["role"] == "assistant":
                        if message.get("intent"):
                            st.caption(f"Intent: {message['intent']} | Status: {message.get('status', 'N/A')}")

            # Chat input
            with st.form(key="chat_form", clear_on_submit=True):
                col_input, col_file = st.columns([3, 1])
                with col_input:
                    prompt = st.text_input("Message", placeholder="Enter your message...")
                with col_file:
                    uploaded_file = st.file_uploader("Upload image", type=["jpg", "png"], label_visibility="collapsed")

                if st.form_submit_button("Send") and customer_id:
                    user_content = prompt or ("Image uploaded" if uploaded_file else "")
                    
                    if user_content or uploaded_file:
                        st.session_state.messages.append({
                            "role": "user",
                            "content": user_content,
                            "timestamp": datetime.now().isoformat()
                        })
                        
                        with st.spinner("Processing..."):
                            response = send_message(prompt, customer_id, uploaded_file)
                            
                        if response:
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": response.get('message', response.get('response', 'Processing...')),
                                "intent": response.get('intent', 'REFUND_REQUEST' if uploaded_file else 'Unknown'),
                                "status": response.get('status', 'Processing'),
                                "timestamp": datetime.now().isoformat()
                            })
                            
                            # Show status
                            if response.get('status') == 'resolved':
                                st.success("✅ Request resolved successfully!")
                            elif response.get('status') == 'escalated':
                                st.warning("⚠️ Request escalated for human review")
                            elif response.get('status') == 'pending_image':
                                st.info("ℹ️ Please upload an image for validation")
                        
                        st.rerun()

    with col2:
        # Customer info
        if customer_id:
            customer_info = get_customer_info(customer_id)
            if customer_info:
                customer = customer_info.get('customer', {})
                st.header("👤 Customer Info")
                st.markdown(f"""
                <div class="customer-info">
                    <strong>Name:</strong> {customer.get('name', 'N/A')}<br>
                    <strong>ID:</strong> {customer.get('customer_id', 'N/A')}<br>
                    <strong>Email:</strong> {customer.get('email', 'N/A')}<br>
                    <strong>Wallet:</strong> ₹{customer.get('wallet_balance', 0)}<br>
                    <strong>Membership:</strong> {customer.get('membership', 'N/A')}<br>
                    <strong>Location:</strong> {customer.get('location', 'N/A')}
                </div>
                """, unsafe_allow_html=True)

        # Quick stats
        st.header("📊 Quick Stats")
        try:
            response = requests.get(f"{API_BASE_URL}/analytics", timeout=5)
            if response.status_code == 200:
                analytics = response.json()
                st.metric("Total Interactions", analytics.get('total_interactions', 0))
                st.metric("Resolution Rate", f"{analytics.get('resolution_rate', 0)}%")
                st.metric("Avg Response Time", f"{analytics.get('avg_response_time', 0)}s")
        except:
            st.info("Analytics unavailable")

def human_agent_page():
    """Human agent dashboard"""
    st.markdown("""
    <div class="main-header">
        <h1>👨‍💼 Human Agent Dashboard</h1>
        <p>Review and resolve escalated customer cases</p>
    </div>
    """, unsafe_allow_html=True)

    # Get escalations
    escalations = get_escalations()
    
    if not escalations:
        st.success("🎉 No escalated cases! All customers are happy.")
        return

    # Filter escalations
    pending_cases = [e for e in escalations if e.get('status') == 'pending']
    resolved_cases = [e for e in escalations if e.get('status') == 'resolved']

    # Stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Pending Cases", len(pending_cases))
    with col2:
        st.metric("Resolved Cases", len(resolved_cases))
    with col3:
        st.metric("Total Cases", len(escalations))

    # Pending cases
    if pending_cases:
        st.subheader("🚨 Pending Cases")
        for case in pending_cases:
            case_id = case.get('case_id', 'Unknown')
            customer_id = case.get('customer_id', 'Unknown')
            issue_details = case.get('issue_details', 'No details')
            
            with st.expander(f"Case {case_id} - Customer {customer_id}"):
                st.text_area("Issue Details", value=issue_details, height=100, disabled=True)
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button(f"✅ Approve", key=f"approve_{case_id}"):
                        if resolve_escalation(case_id, "approved", "Approved by human agent"):
                            st.success("Case approved!")
                            st.rerun()
                
                with col2:
                    if st.button(f"❌ Reject", key=f"reject_{case_id}"):
                        if resolve_escalation(case_id, "rejected", "Rejected after review"):
                            st.success("Case rejected!")
                            st.rerun()
                
                with col3:
                    if st.button(f"📞 Contact", key=f"contact_{case_id}"):
                        if resolve_escalation(case_id, "contact_required", "Customer contact needed"):
                            st.success("Marked for contact!")
                            st.rerun()

def main():
    """Main application"""
    # Start backend
    with st.spinner("Starting backend services..."):
        if not start_backend():
            st.error("❌ Failed to start backend. Please check your setup.")
            st.info("Make sure you have set the required environment variables:")
            st.code("""
GROQ_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
MONGODB_URI=your_connection_string
            """)
            return

    # Navigation
    st.sidebar.title("🛒 CARE System")
    page = st.sidebar.selectbox(
        "Navigate to:",
        ["Customer Support", "Human Agent Dashboard", "API Status"]
    )

    if page == "Customer Support":
        customer_support_page()
    elif page == "Human Agent Dashboard":
        human_agent_page()
    elif page == "API Status":
        st.header("🔧 API Status")
        try:
            response = requests.get(f"{API_BASE_URL}/health", timeout=5)
            if response.status_code == 200:
                st.success("✅ Backend API is running")
                st.json(response.json())
            else:
                st.error(f"❌ Backend API error: {response.status_code}")
        except Exception as e:
            st.error(f"❌ Cannot connect to backend: {e}")
        
        st.subheader("🔗 API Endpoints")
        st.markdown(f"""
        - **Health Check**: {API_BASE_URL}/health
        - **API Docs**: {API_BASE_URL}/docs
        - **Customers**: {API_BASE_URL}/customers
        - **Chat**: {API_BASE_URL}/chat
        - **Validate**: {API_BASE_URL}/validate
        """)

if __name__ == "__main__":
    main()