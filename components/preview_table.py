import streamlit as st
import pandas as pd
from utils.logger import get_logger

logger = get_logger(__name__)

def display_invoice_table():
    """Renders the data table of uploaded invoices."""
    st.markdown("### Uploaded Invoices Preview")
    
    invoices = st.session_state.get("uploaded_invoices", [])
    
    if not invoices:
        st.info("No invoices uploaded yet. Use the Upload Section to add files.")
        return

    # Filter metrics
    total = len(invoices)
    total_uploaded = sum(1 for inv in invoices if inv["Status"] == "UPLOADED")
    total_ready = sum(1 for inv in invoices if inv["Status"] in ["READY_FOR_PROCESSING", "PROCESSING"])
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Invoices", total)
    col2.metric("Pending Start", total_uploaded)
    col3.metric("Ready / In Pipeline", total_ready)

    # Convert to dataframe
    df = pd.DataFrame(invoices)
    
    # Reorder columns slightly for better view
    cols = ["Invoice File Name", "Upload Time", "File Size (KB)", "Upload Method", "Status"]
    df = df[cols]
    
    # Function to add emojis for visual appeal
    def get_status_emoji(status):
        status_map = {
            "UPLOADED": "🔵 UPLOADED",
            "READY_FOR_PROCESSING": "🟡 READY",
            "PROCESSING": "🟢 PROCESSING",
            "ERROR": "🔴 ERROR"
        }
        return status_map.get(status, status)

    df["Status"] = df["Status"].apply(get_status_emoji)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Status": st.column_config.TextColumn(
                "Status",
                help="The processing status of the invoice"
            )
        }
    )
