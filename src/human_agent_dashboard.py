#!/usr/bin/env python3
"""
Human Agent Dashboard for reviewing and resolving escalated cases
"""
import streamlit as st
import requests
import json
from datetime import datetime
import base64
from PIL import Image
from io import BytesIO
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
# Determine API base URL based on environment
if os.getenv("SPACE_ID"):  # Running on Hugging Face Spaces
    API_BASE_URL = "http://localhost:7860"  # Internal communication
else:
    API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:5000")  # Local development

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

# Page configuration
st.set_page_config(
    page_title="CARE: Human Agent Dashboard",
    page_icon="👨‍💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .escalation-card {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 12px;
        border-left: 6px solid #dc3545;
        margin-bottom: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .resolved-card {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 12px;
        border-left: 6px solid #28a745;
        margin-bottom: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .high-priority {
        border-left-color: #dc3545 !important;
    }
    .medium-priority {
        border-left-color: #ffc107 !important;
    }
    .low-priority {
        border-left-color: #17a2b8 !important;
    }
    .case-header {
        font-size: 1.2rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
    }
    .case-details {
        font-size: 0.9rem;
        color: #6c757d;
    }
    .action-buttons {
        margin-top: 1rem;
    }
</style>
""", unsafe_allow_html=True)

def get_all_escalations():
    """Fetch all escalated cases"""
    try:
        response = requests.get(f"{API_BASE_URL}/escalations/all", timeout=10)
        if response.status_code == 200:
            return response.json().get('escalations', [])
        else:
            st.error(f"Failed to fetch escalations: HTTP {response.status_code}")
            return []
    except requests.exceptions.RequestException as e:
        st.error(f"Error connecting to API: {e}")
        return []

def get_escalation_details(case_id):
    """Get detailed information about a specific escalation"""
    try:
        response = requests.get(f"{API_BASE_URL}/escalation/{case_id}", timeout=10)
        if response.status_code == 200:
            return response.json().get('escalation')
        else:
            st.error(f"Failed to fetch escalation details: HTTP {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching escalation details: {e}")
        return None

def resolve_escalation(case_id, resolution_type, notes, refund_amount=None):
    """Resolve an escalated case"""
    try:
        resolution_data = {
            "resolution_type": resolution_type,
            "notes": notes,
            "resolved_by": "Human Agent",
            "resolved_at": datetime.now().isoformat(),
            "refund_amount": refund_amount
        }
        
        response = requests.post(
            f"{API_BASE_URL}/escalation/{case_id}/resolve", 
            json=resolution_data, 
            timeout=10
        )
        
        if response.status_code == 200:
            return True
        else:
            st.error(f"Failed to resolve case: HTTP {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        st.error(f"Error resolving case: {e}")
        return False

def get_customer_info(customer_id):
    """Get customer information"""
    try:
        response = requests.get(f"{API_BASE_URL}/customer/{customer_id}", timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def display_escalation_card(escalation):
    """Display an escalation case card"""
    case_id = escalation.get('case_id', 'Unknown')
    customer_id = escalation.get('customer_id', 'Unknown')
    status = escalation.get('status', 'pending')
    escalation_time = escalation.get('escalation_time', 'Unknown')
    issue_details = escalation.get('issue_details', 'No details available')
    
    # Determine priority based on issue content
    priority = "high"
    if "refund" in issue_details.lower():
        priority = "high"
    elif "wallet" in issue_details.lower():
        priority = "medium"
    else:
        priority = "low"
    
    # Parse issue details if it's JSON
    parsed_details = None
    try:
        if issue_details.startswith('Refund validation escalated:'):
            json_part = issue_details.split('Refund validation escalated: ')[1]
            parsed_details = json.loads(json_part)
    except:
        pass
    
    card_class = "resolved-card" if status == "resolved" else "escalation-card"
    priority_class = f"{priority}-priority"
    
    st.markdown(f"""
    <div class="{card_class} {priority_class}">
        <div class="case-header">
            🚨 Case ID: {case_id}
        </div>
        <div class="case-details">
            <strong>Customer:</strong> {customer_id}<br>
            <strong>Status:</strong> {status.upper()}<br>
            <strong>Priority:</strong> {priority.upper()}<br>
            <strong>Escalated:</strong> {escalation_time}<br>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Show detailed information
    with st.expander(f"📋 Case Details - {case_id}"):
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.write("**Issue Details:**")
            st.text_area("", value=issue_details, height=100, disabled=True, key=f"details_{case_id}")
            
            if parsed_details:
                st.write("**Parsed Details:**")
                st.json(parsed_details)
                
                # Show validation result if available
                if 'validation_result' in parsed_details:
                    validation = parsed_details['validation_result']
                    st.write("**AI Analysis:**")
                    st.write(f"- **Confidence:** {validation.get('confidence', 'N/A')}")
                    st.write(f"- **Reason:** {validation.get('reason', 'N/A')}")
                    st.write(f"- **AI Decision:** {validation.get('message', 'N/A')}")
        
        with col2:
            # Get customer info
            customer_info = get_customer_info(customer_id)
            if customer_info:
                customer = customer_info.get('customer', {})
                st.write("**Customer Info:**")
                st.write(f"**Name:** {customer.get('name', 'N/A')}")
                st.write(f"**Email:** {customer.get('email', 'N/A')}")
                st.write(f"**Wallet:** ₹{customer.get('wallet_balance', 0)}")
                st.write(f"**Membership:** {customer.get('membership', 'N/A')}")
        
        # Resolution actions (only for pending cases)
        if status == "pending":
            st.write("---")
            st.write("**🔧 Resolution Actions:**")
            
            col_action1, col_action2, col_action3 = st.columns(3)
            
            with col_action1:
                if st.button(f"✅ Approve Refund", key=f"approve_{case_id}"):
                    refund_amount = parsed_details.get('refund_amount', 100.0) if parsed_details else 100.0
                    if resolve_escalation(case_id, "approved", f"Refund approved by human agent", refund_amount):
                        st.success(f"✅ Case {case_id} approved!")
                        st.rerun()
            
            with col_action2:
                if st.button(f"❌ Reject Request", key=f"reject_{case_id}"):
                    if resolve_escalation(case_id, "rejected", "Request rejected after human review"):
                        st.success(f"❌ Case {case_id} rejected!")
                        st.rerun()
            
            with col_action3:
                if st.button(f"📞 Contact Customer", key=f"contact_{case_id}"):
                    if resolve_escalation(case_id, "contact_required", "Customer contact required for clarification"):
                        st.success(f"📞 Case {case_id} marked for customer contact!")
                        st.rerun()
            
            # Custom resolution
            with st.form(f"custom_resolution_{case_id}"):
                st.write("**Custom Resolution:**")
                custom_notes = st.text_area("Resolution Notes", key=f"notes_{case_id}")
                custom_refund = st.number_input("Refund Amount (if applicable)", min_value=0.0, key=f"refund_{case_id}")
                
                if st.form_submit_button("🔧 Apply Custom Resolution"):
                    if custom_notes:
                        if resolve_escalation(case_id, "custom", custom_notes, custom_refund if custom_refund > 0 else None):
                            st.success(f"🔧 Custom resolution applied to case {case_id}!")
                            st.rerun()
                    else:
                        st.error("Please provide resolution notes")

def main():
    st.title("👨‍💼 CARE: Human Agent Dashboard")
    st.markdown("**Manage escalated customer support cases**")
    
    # Sidebar filters
    with st.sidebar:
        st.header("🔍 Filters")
        status_filter = st.selectbox("Status", ["All", "Pending", "Resolved"])
        priority_filter = st.selectbox("Priority", ["All", "High", "Medium", "Low"])
        
        st.header("📊 Quick Stats")
        escalations = get_all_escalations()
        
        if escalations:
            pending_count = len([e for e in escalations if e.get('status') == 'pending'])
            resolved_count = len([e for e in escalations if e.get('status') == 'resolved'])
            
            st.metric("Pending Cases", pending_count)
            st.metric("Resolved Cases", resolved_count)
            st.metric("Total Cases", len(escalations))
        else:
            st.info("No escalation data available")
    
    # Main content
    if st.button("🔄 Refresh Cases"):
        st.rerun()
    
    escalations = get_all_escalations()
    
    if not escalations:
        st.info("🎉 No escalated cases found! All customers are happy.")
        return
    
    # Filter escalations
    filtered_escalations = escalations
    
    if status_filter != "All":
        filtered_escalations = [e for e in filtered_escalations if e.get('status', '').lower() == status_filter.lower()]
    
    # Display escalations
    st.write(f"**📋 Showing {len(filtered_escalations)} cases**")
    
    # Separate pending and resolved cases
    pending_cases = [e for e in filtered_escalations if e.get('status') == 'pending']
    resolved_cases = [e for e in filtered_escalations if e.get('status') == 'resolved']
    
    # Show pending cases first
    if pending_cases:
        st.subheader("🚨 Pending Cases (Require Action)")
        for escalation in pending_cases:
            display_escalation_card(escalation)
    
    # Show resolved cases
    if resolved_cases:
        st.subheader("✅ Resolved Cases")
        for escalation in resolved_cases:
            display_escalation_card(escalation)

if __name__ == "__main__":
    main()