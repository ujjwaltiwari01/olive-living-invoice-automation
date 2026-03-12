from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

def validate_financial_rules(mapped_data: dict) -> list[str]:
    """
    Executes a deterministic validation engine against the Zoho Schema mapped payload.
    Returns a list of error strings. If list is empty, validation passed.
    """
    errors = []
    
    def safe_str_strip(val):
        return str(val).strip() if val is not None else ""

    invoice_num = safe_str_strip(mapped_data.get("Invoice Number"))
    invoice_date_str = safe_str_strip(mapped_data.get("Invoice Date"))
    due_date_str = safe_str_strip(mapped_data.get("Due Date"))
    customer_name = safe_str_strip(mapped_data.get("Customer Name"))
    line_items = mapped_data.get("line_items")
    line_items = line_items if isinstance(line_items, list) else []
    gstin = safe_str_strip(mapped_data.get("GST Identification Number (GSTIN)"))
    
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
    calculated_total_if_inclusive = 0.0
    
    for idx, item in enumerate(line_items):
        try:
            qty = float(item.get("Quantity", 0))
            price = float(item.get("Item Price", 0))
            tax_perc = float(item.get("Item Tax %", 0))
            is_inclusive = bool(item.get("Is Inclusive Tax", False))
            
            if qty < 0:
                errors.append(f"Numeric Validation Failure (Line {idx+1}): Quantity cannot be negative.")
            if price < 0:
                errors.append(f"Numeric Validation Failure (Line {idx+1}): Item Price cannot be negative.")
            if tax_perc < 0:
                 errors.append(f"Numeric Validation Failure (Line {idx+1}): Tax % cannot be negative.")
                 
            # Simple total calc: Qty * Price * (1 + Tax%) if exclusive, just Qty * Price if inclusive (tax is bundled)
            if is_inclusive:
                line_total = qty * price
            else:
                line_total = (qty * price) * (1 + (tax_perc / 100))
                
            calculated_total += line_total
            calculated_total_if_inclusive += qty * price
            
        except (ValueError, TypeError):
             errors.append(f"Numeric Validation Failure (Line {idx+1}): Non-numeric values found in Quantity or Price.")
             
    # 4. Amount Consistency
    bypass_math = mapped_data.get("Bypass Math", False)
    total_amount = float(mapped_data.get("total_amount", 0.0) or 0.0)
    
    # 4.1 Apply Top-Level Adjustments mapping to Indian tax
    tcs_amount = float(mapped_data.get("TCS Amount", 0.0) or 0.0)
    tds_amount = float(mapped_data.get("TDS Amount", 0.0) or 0.0)
    
    # TCS is an added charge, TDS is a deducted charge
    calculated_total += tcs_amount
    calculated_total -= tds_amount
    calculated_total_if_inclusive += tcs_amount
    calculated_total_if_inclusive -= tds_amount
    
    # Only run amount consistency check if Total Amount was actually extracted/provided
    if bypass_math:
        logger.info(f"Amount Consistency: User bypassed line-item math check for '{invoice_num}'.")
    elif total_amount > 0:
        tolerance = 1.0  # Allow for small rounding differences (e.g. 0.01 cents)
        if abs(calculated_total - total_amount) > tolerance:
            # Smart Fallback: Check if treating ALL items as tax-inclusive perfectly matches the total
            if abs(calculated_total_if_inclusive - total_amount) <= tolerance:
                logger.info(f"Amount Consistency: Standard check failed but Auto-Inclusive check perfectly matches {total_amount}. Passing validation.")
            else:
                errors.append(f"Amount Consistency Failure: Sum of line items ({calculated_total:.2f}) does not match Total Amount ({total_amount:.2f}).")

    # 5. GST Logic
    # If any line item has tax, GSTIN should technically be present (only enforce strictly if currency is INR and it's a B2B transaction)
    has_tax = False
    for i in line_items:
        try:
            val = i.get("Item Tax %")
            if val is not None and float(val) > 0:
                has_tax = True
                break
        except (ValueError, TypeError):
            pass

    currency_raw = mapped_data.get("Currency Code")
    currency = str(currency_raw).upper() if currency_raw is not None else "INR"
    gst_treatment = mapped_data.get("GST Treatment", "")
    
    if has_tax and not gstin and currency == "INR" and gst_treatment == "business_gst":
        errors.append("GST Logic Failure: Tax % applied for INR B2B invoice but GSTIN is missing.")

    if errors:
        logger.warning(f"VALIDATION_FAILED: {len(errors)} errors found for invoice '{invoice_num}'")
        for err in errors:
            logger.debug(f"Validation Error: {err}")
    else:
        logger.info(f"Financial validation passed for invoice '{invoice_num}'.")

    return errors
