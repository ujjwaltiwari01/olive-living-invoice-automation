import streamlit as st
import pandas as pd
from typing import Dict, Any
from utils.logger import get_logger
from utils.financial_validation import validate_financial_rules, compute_confidence_score

logger = get_logger(__name__)

def _display_line_items_editor(mapped_data: Dict[str, Any]) -> list:
    """
    Renders an editable data editor for line items.
    Allows user to add/delete/modify rows directly.
    """
    st.markdown("##### Line Items")
    
    # Initialize an empty row if parsing failed completely but invoice exists
    lines = mapped_data.get("line_items", [])
    if not lines:
        lines = [{"Item Name": "", "Item Desc": "", "Quantity": 1.0, "Item Price": 0.0, "Item Tax %": 0.0, "Is Inclusive Tax": False, "HSN/SAC": ""}]
    else:
        # Guarantee missing boolean exists to prevent column render mismatch on old cache
        for l in lines:
            if "Is Inclusive Tax" not in l:
                l["Is Inclusive Tax"] = False
                
    df = pd.DataFrame(lines)
    
    # Configuration for the editor
    config = {
        "Item Name": st.column_config.TextColumn("Item Name", required=True),
        "Item Desc": st.column_config.TextColumn("Item Desc"),
        "Quantity": st.column_config.NumberColumn("Quantity", min_value=0.0, format="%.2f"),
        "Item Price": st.column_config.NumberColumn("Item Price", min_value=0.0, format="%.2f"),
        "Item Tax %": st.column_config.NumberColumn("Tax %", min_value=0.0, max_value=100.0, format="%.2f"),
        "Is Inclusive Tax": st.column_config.CheckboxColumn("Tax Inclusive?", default=False),
        "HSN/SAC": st.column_config.TextColumn("HSN/SAC")
    }

    edited_df = st.data_editor(
        df,
        column_config=config,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=f"editor_{mapped_data.get('Invoice Number', 'new')}"
    )
    
    return edited_df.to_dict('records')


def display_verification_interface():
    """
    Renders the iterative invoice verification interface.
    Allows passing through UNDER_REVIEW invoices until they are READY_FOR_ZOHO.
    """
    if "invoice_records" not in st.session_state:
        st.info("No invoices available for verification.")
        return

    records = st.session_state.invoice_records
    
    # Filter to only invoices waiting for review
    review_queue = [r for r in records if r["status"] in ["UNDER_REVIEW", "NEEDS_ATTENTION", "INCOMPLETE_DATA"]]
    
    if not review_queue:
        st.success("🎉 All invoices have been verified!")
        return
        
    # We always show the first item in the queue for sequential processing
    current_record = review_queue[0]
    idx = records.index(current_record)
    mapped_data = current_record.get("mapped_data", {})
    
    st.markdown(f"### Verification Queue: {len(review_queue)} remaining")
    st.caption(f"Currently reviewing source file: `{current_record['filename']}`")

    # L7: Confidence Score Badge
    load_errors = validate_financial_rules(mapped_data)
    confidence = compute_confidence_score(mapped_data, load_errors)
    if confidence >= 0.8:
        score_color = "#2ecc71"   # green
        score_label = "High"
    elif confidence >= 0.5:
        score_color = "#f39c12"   # orange
        score_label = "Medium"
    else:
        score_color = "#e74c3c"   # red
        score_label = "Low"

    st.markdown(
        f"""
        <div style='display:flex; align-items:center; gap:12px; margin-bottom:8px;'>
            <span style='font-size:0.9rem; color:#888;'>AI Confidence:</span>
            <span style='background:{score_color}22; color:{score_color}; border:1px solid {score_color};
                         border-radius:20px; padding:2px 14px; font-size:0.9rem; font-weight:600;'>
                {score_label} ({confidence:.0%})
            </span>
        </div>
        """,
        unsafe_allow_html=True
    )

    # LLM retry warnings (items the self-healing loop could not fix)
    llm_warnings = mapped_data.get("_math_warnings", [])
    if llm_warnings:
        with st.expander("⚠️ AI could not auto-correct these issues (review carefully)", expanded=True):
            for w in llm_warnings:
                st.warning(w)

    if load_errors:
        st.warning("⚠️ Validation Issues Found:")
        for err in load_errors:
            st.error(err)
            
    if current_record["status"] == "INCOMPLETE_DATA":
        st.error("Document AI completely missed critical fields. Please fill manually.")

    with st.form(key=f"verify_form_{idx}"):
        
        col1, col2, col3 = st.columns(3)
        with col1:
            inv_num = st.text_input("Invoice Number *", value=mapped_data.get("Invoice Number") or "")
            inv_date = st.text_input("Invoice Date (YYYY-MM-DD) *", value=mapped_data.get("Invoice Date") or "")
            
        with col2:
            cust_name = st.text_input("Customer/Supplier Name *", value=mapped_data.get("Customer Name") or "")
            due_date = st.text_input("Due Date (YYYY-MM-DD)", value=mapped_data.get("Due Date") or "")
            
        with col3:
            gstin = st.text_input("GSTIN", value=mapped_data.get("GST Identification Number (GSTIN)") or "")
            curr = st.text_input("Currency Code", value=mapped_data.get("Currency Code") or "INR")
            
        col4, col5 = st.columns(2)
        with col4:
            total_v = mapped_data.get("total_amount")
            total_amt_input = st.text_input("Expected Total Amount", value=str(total_v) if total_v is not None else "0.0")
            
            tcs_v = mapped_data.get("TCS Amount")
            tcs_amt_input = st.text_input("TCS Amount", value=str(tcs_v) if tcs_v is not None else "0.0")
            
            notes = st.text_area("Notes", value=mapped_data.get("Notes") or "")
        with col5:
            tax_v = mapped_data.get("tax_amount")
            tax_amt_input = st.text_input("Expected Tax Amount", value=str(tax_v) if tax_v is not None else "0.0")
            
            tds_v = mapped_data.get("TDS Amount")
            tds_amt_input = st.text_input("TDS Amount", value=str(tds_v) if tds_v is not None else "0.0")
            
        bypass_math = st.checkbox(
            "⚠️ Bypass Line Item Math (Consolidated Invoice)", 
            value=mapped_data.get("Bypass Math", False), 
            help="Check this if the invoice only has a grand total and individual line prices are missing/hallucinated by OCR."
        )
        
        # Line Items
        updated_lines = _display_line_items_editor(mapped_data)
        
        st.divider()
        
        # Action Buttons
        a_col1, a_col2, a_col3, a_col4 = st.columns([1, 1.2, 1, 3])
        
        submit_approve = a_col1.form_submit_button("✅ Approve", type="primary")
        submit_force = a_col2.form_submit_button("⚡ Force Approve", help="Bypass all validation errors and approve anyway.")
        submit_flag = a_col3.form_submit_button("🚩 Flag Issue")
        submit_reject = a_col4.form_submit_button("❌ Reject")
        
        if submit_approve or submit_force or submit_flag or submit_reject:
            # Reconstruct the schema payload with user edits
            try:
                total_val = float(total_amt_input)
            except ValueError:
                total_val = 0.0
                
            try:
                tax_val = float(tax_amt_input)
            except ValueError:
                tax_val = 0.0
                
            try:
                tcs_val = float(tcs_amt_input)
            except ValueError:
                tcs_val = 0.0
                
            try:
                tds_val = float(tds_amt_input)
            except ValueError:
                tds_val = 0.0
                
            edited_payload = mapped_data.copy()
            edited_payload.update({
                "Invoice Number": inv_num,
                "Invoice Date": inv_date,
                "Due Date": due_date,
                "Customer Name": cust_name,
                "Currency Code": curr,
                "GST Identification Number (GSTIN)": gstin,
                "Notes": notes,
                "total_amount": total_val,
                "tax_amount": tax_val,
                "TCS Amount": tcs_val,
                "TDS Amount": tds_val,
                "Bypass Math": bypass_math,
                "line_items": updated_lines
            })
            
            # Re-run validation on edited data
            final_errors = validate_financial_rules(edited_payload)
            
            if submit_approve or submit_force:
                if submit_approve and final_errors:
                    st.error("Cannot approve: Validation failed. Please fix the errors above or use 'Force Approve'.")
                else:
                    if submit_force and final_errors:
                        edited_payload["bypassed_errors"] = final_errors
                        logger.warning(f"INVOICE_FORCE_APPROVED: {current_record['filename']} with errors: {final_errors}")
                    
                    st.session_state.invoice_records[idx]["mapped_data"] = edited_payload
                    st.session_state.invoice_records[idx]["status"] = "VERIFIED"
                    st.session_state.invoice_records[idx]["verified_payload"] = edited_payload
                    logger.info(f"INVOICE_VERIFIED: {current_record['filename']}")
                    st.rerun()
                    
            elif submit_flag:
                st.session_state.invoice_records[idx]["mapped_data"] = edited_payload
                st.session_state.invoice_records[idx]["status"] = "NEEDS_ATTENTION"
                st.session_state.invoice_records[idx]["validation_errors"] = final_errors
                logger.info(f"INVOICE_FLAGGED: {current_record['filename']}")
                
                # Move to back of list to continue sequential processing
                popped = st.session_state.invoice_records.pop(idx)
                st.session_state.invoice_records.append(popped)
                st.rerun()
                
            elif submit_reject:
                st.session_state.invoice_records[idx]["status"] = "REJECTED"
                logger.info(f"INVOICE_REJECTED: {current_record['filename']}")
                st.rerun()
