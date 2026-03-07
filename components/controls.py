import streamlit as st
import time
from utils.document_ai import process_batch_invoices
from utils.logger import get_logger

logger = get_logger(__name__)

def handle_processing():
    """
    Sends uploaded invoices to the Document AI OCR pipeline.
    Updates states, displays a progress bar, and logs extraction facts.
    """
    invoices = st.session_state.uploaded_invoices
    
    # Filter only those that are UPLOADED
    to_process = [inv for inv in invoices if inv["Status"] == "UPLOADED"]
    
    if not to_process:
        st.warning("No new invoices to process. Please upload some first.")
        return

    logger.info(f"Starting actual OCR pipeline for {len(to_process)} invoices.")

    progress_bar = st.progress(0, text="Preparing Document AI pipeline...")
    
    from utils.zoho_mapper import normalize_ocr_data, map_to_zoho_schema
    
    # Execute batch processing (synchronous with individual retries inside document_ai)
    results = process_batch_invoices(to_process, progress_bar)
    
    # Keep track of the structured response globally
    if "extracted_data" not in st.session_state:
        st.session_state.extracted_data = []
        
    # Maintain proper Verification Queue state
    if "invoice_records" not in st.session_state:
        st.session_state.invoice_records = []
        
    for res in results:
        if res["status"] in ["processed", "ocr_failed", "validation_error"]:
            filename = res["filename"]
            raw_data = res.get("data", {})
            
            # Phase 1: Normalize
            normalized = normalize_ocr_data(raw_data)
            
            # Phase 2: Map to Zoho (Draft)
            mapped = map_to_zoho_schema(normalized)
            
            # Phase 3: Setup state for Human Verification
            record_status = "UNDER_REVIEW"
            if res["status"] != "processed":
                record_status = "INCOMPLETE_DATA" # Failed OCR but still pushes to manual review via UI
                
            new_record = {
                "filename": filename,
                "status": record_status,
                "ocr_data": raw_data,
                "mapped_data": mapped,
                "validation_errors": [],
                "verified_payload": None
            }
            
            st.session_state.invoice_records.append(new_record)

    # Force the original state object to sync correctly and wipe references (safety)
    st.session_state.uploaded_invoices = invoices
    progress_bar.progress(100, text="OCR pipeline completed! Moving to Verification.")
    
    if results:
        st.success(f"Completed Document AI processing for {len(to_process)} invoices.")
    logger.info("Pipeline processing completed.")

def display_processing_controls():
    """Renders action buttons to process layout or clear queue."""
    st.markdown("### Process Actions")
    st.markdown("Trigger the pipeline to extract data from uploaded invoices.")
    
    col1, col2, _ = st.columns([1.5, 1.5, 4])
    
    with col1:
        if st.button("🚀 Process Invoices", use_container_width=True, type="primary"):
            handle_processing()
            st.rerun()
            
    with col2:
        if st.button("🗑️ Clear Queue", use_container_width=True):
            st.session_state.uploaded_invoices = []
            st.success("Upload queue cleared.")
            logger.info("User cleared the upload queue.")
            st.rerun()
