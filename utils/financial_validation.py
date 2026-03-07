from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

def validate_financial_rules(mapped_data: dict) -> list[str]:
    """
    Executes a deterministic validation engine against the Zoho Schema mapped payload.
    Returns a list of error strings. If list is empty, validation passed.
    """
    errors = []
    
    invoice_num = mapped_data.get("Invoice Number", "").strip()
    invoice_date_str = mapped_data.get("Invoice Date", "").strip()
    due_date_str = mapped_data.get("Due Date", "").strip()
    customer_name = mapped_data.get("Customer Name", "").strip()
    line_items = mapped_data.get("line_items", [])
    gstin = mapped_data.get("GST Identification Number", "").strip()
    
    # 1. Integrity Validations
    if not invoice_num:
        errors.append("Invoice Integrity Failure: Invoice Number is empty.")
        
    if not customer_name:
        errors.append("Invoice Integrity Failure: Customer (Supplier) Name is empty.")
        
    if not line_items:
        errors.append("Invoice Integrity Failure: At least one line item is required.")

    # 2. Date Validations
    inv_date_obj = None
    due_date_obj = None
    
    if not invoice_date_str:
        errors.append("Date Validation Failure: Invoice Date is required.")
    else:
        try:
            inv_date_obj = datetime.strptime(invoice_date_str, "%Y-%m-%d")
        except ValueError:
            errors.append(f"Date Validation Failure: Invalid Invoice Date format '{invoice_date_str}'. Expected ISO.")
            
    if due_date_str:
        try:
            due_date_obj = datetime.strptime(due_date_str, "%Y-%m-%d")
        except ValueError:
             errors.append(f"Date Validation Failure: Invalid Due Date format '{due_date_str}'. Expected ISO.")
             
    if inv_date_obj and due_date_obj:
        if inv_date_obj > due_date_obj:
            errors.append("Date Validation Failure: Invoice Date cannot be after Due Date.")
            
    # 3. Numeric & Logic Validations on Line Items
    calculated_total = 0.0
    for idx, item in enumerate(line_items):
        try:
            qty = float(item.get("Quantity", 0))
            price = float(item.get("Item Price", 0))
            tax_perc = float(item.get("Item Tax %", 0))
            
            if qty < 0:
                errors.append(f"Numeric Validation Failure (Line {idx+1}): Quantity cannot be negative.")
            if price < 0:
                errors.append(f"Numeric Validation Failure (Line {idx+1}): Item Price cannot be negative.")
            if tax_perc < 0:
                 errors.append(f"Numeric Validation Failure (Line {idx+1}): Tax % cannot be negative.")
                 
            # Simple total calc: Qty * Price * (1 + Tax%)
            line_total = (qty * price) * (1 + (tax_perc / 100))
            calculated_total += line_total
            
        except (ValueError, TypeError):
             errors.append(f"Numeric Validation Failure (Line {idx+1}): Non-numeric values found in Quantity or Price.")
             
    # 4. Amount Consistency
    total_amount = float(mapped_data.get("Total Amount", 0.0) or 0.0)
    
    # Only run amount consistency check if Total Amount was actually extracted/provided
    if total_amount > 0:
        tolerance = 1.0  # Allow for small rounding differences (e.g. 0.01 cents)
        if abs(calculated_total - total_amount) > tolerance:
            errors.append(f"Amount Consistency Failure: Sum of line items ({calculated_total:.2f}) does not match Total Amount ({total_amount:.2f}).")

    # 5. GST Logic
    # If any line item has tax, GSTIN should technically be present (only enforce strictly if currency is INR to prevent blocking international invoices)
    has_tax = any(float(i.get("Item Tax %", 0)) > 0 for i in line_items)
    currency = mapped_data.get("Currency Code", "INR").upper()
    if has_tax and not gstin and currency == "INR":
        errors.append("GST Logic Failure: Tax % applied for INR invoice but GSTIN is missing.")

    if errors:
        logger.warning(f"VALIDATION_FAILED: {len(errors)} errors found for invoice '{invoice_num}'")
        for err in errors:
            logger.debug(f"Validation Error: {err}")
    else:
        logger.info(f"Financial validation passed for invoice '{invoice_num}'.")

    return errors
