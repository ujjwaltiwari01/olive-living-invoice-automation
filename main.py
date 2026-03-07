import streamlit as st
import pandas as pd
from utils.logger import get_logger
from components.upload import display_upload_section
from components.preview_table import display_invoice_table
from components.controls import display_processing_controls
from components.verification import display_verification_interface

logger = get_logger(__name__)

def initialize_session_state():
    """Initializes session state variables if they don't exist."""
    if "uploaded_invoices" not in st.session_state:
        st.session_state.uploaded_invoices = []
        logger.info("Session state initialized.")
    if "invoice_records" not in st.session_state:
        st.session_state.invoice_records = []

def main():
    st.set_page_config(
        page_title="Olive Invoice Automation",
        page_icon="🧾",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    initialize_session_state()

    # Sidebar for additional settings/info
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/2936/2936630.png", width=50)
        st.markdown("## Olive Automation")
        st.markdown("Automate your invoice ingestion pipeline with ease.")
        st.info("System Status: **Online** 🟢")

    # Header Section
    col1, col2 = st.columns([1, 15])
    with col1:
        st.image("https://cdn-icons-png.flaticon.com/512/3135/3135694.png", width=60)
    with col2:
        st.title("Invoice Dashboard")
        st.markdown("<p style='font-size: 1.1rem; color: gray; margin-top: -10px;'>Upload and manage invoices for automated Document AI processing</p>", unsafe_allow_html=True)
    
    st.divider()

    # Main Layout
    
    # 1. Upload Section
    display_upload_section()
    st.divider()

    # 2. Uploaded Invoice Preview Table
    display_invoice_table()
    st.divider()

    # 3. Processing Controls
    display_processing_controls()
    st.divider()
    
    # 4. Human-In-The-Loop Verification Interface
    display_verification_interface()
    
    # 5. Extracted & Verified Invoice Data Section
    # Draw from our new 'invoice_records' tracking logic in Task 3
    verified_records = [r for r in st.session_state.invoice_records if r["status"] == "VERIFIED"]
    
    if verified_records:
        st.divider()
        st.markdown("### ✨ Verified Invoice Data (Ready for ERP)")
        
        flat_results = []
        for v in verified_records:
            payload = v["verified_payload"]
            
            # Simple aggregation to show high-level view (similar to requirements doc)
            total_amt = sum((float(i.get('Quantity', 0)) * float(i.get('Item Price', 0))) * (1 + (float(i.get('Item Tax %', 0)) / 100)) for i in payload.get('line_items', []))
            
            flat_results.append({
                "Source File": v["filename"],
                "Supplier": payload.get("Customer Name", ""),
                "Invoice Number": payload.get("Invoice Number", ""),
                "Date": payload.get("Invoice Date", ""),
                "Total Amount": round(total_amt, 2),
                "Currency": payload.get("Currency Code", "INR"),
                "Line Items": len(payload.get('line_items', []))
            })
            
        extracted_df = pd.DataFrame(flat_results)
        st.dataframe(extracted_df, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
