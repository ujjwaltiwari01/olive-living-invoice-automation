import re
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

# GSTIN: 15-char format  ##AAAAA####A#Z#
_GSTIN_RE = re.compile(r'^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]$')

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
    # If any line item has tax, GSTIN should technically be present
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

    # 6. L6: GSTIN format check (when present)
    if gstin:
        clean_gstin = gstin.strip().upper().replace(" ", "")
        if not _GSTIN_RE.match(clean_gstin):
            errors.append(
                f"GSTIN Format Failure: '{gstin}' is not a valid 15-char Indian GSTIN "
                f"(format: ##AAAAA####A#Z#). Got {len(clean_gstin)} chars."
            )

    # 7. L6: Zero-rate item check (flags LLM extraction errors)
    zero_rate_items = [
        f"Line {idx+1}: '{i.get('Item Name', 'Unknown')}'"
        for idx, i in enumerate(line_items)
        if (i.get("Item Price") or 0) == 0
    ]
    if zero_rate_items:
        errors.append(
            f"Zero Rate Warning: {len(zero_rate_items)} item(s) have Item Price=0 — "
            f"likely extraction errors: {', '.join(zero_rate_items)}"
        )

    # 8. L6: Surface any unresolved math warnings from the LLM retry loop
    llm_warnings = mapped_data.get("_math_warnings", [])
    if llm_warnings:
        for w in llm_warnings:
            errors.append(f"LLM Math Warning (unresolved after retries): {w}")

    if errors:
        logger.warning(f"VALIDATION_FAILED: {len(errors)} errors found for invoice '{invoice_num}'")
        for err in errors:
            logger.debug(f"Validation Error: {err}")
    else:
        logger.info(f"Financial validation passed for invoice '{invoice_num}'.")

    return errors


def compute_confidence_score(mapped_data: dict, fin_errors: list) -> float:
    """
    L7: Computes a 0.0–1.0 confidence score for the extraction quality.
    Used in the HITL UI to prioritize which invoices need human attention.

    Score deductions:
      -0.35 for financial validation errors (math/amount issues)
      -0.10 per zero-rate line item
      -0.20 for missing GSTIN on a B2B invoice
      -0.15 for suspicious invoice number (empty, ::, or purely numeric)
      -0.10 for missing customer name
      -0.15 for LLM math warnings that survived retries
    """
    score = 1.0

    # Penalize for financial errors
    amount_errors = [e for e in fin_errors if "Consistency" in e or "Math" in e]
    if amount_errors:
        score -= 0.35

    # Penalize per zero-rate line item
    zero_rates = sum(
        1 for i in mapped_data.get("line_items", [])
        if (i.get("Item Price") or 0) == 0
    )
    score -= zero_rates * 0.10

    # Penalize for missing/invalid GSTIN on B2B
    gstin = mapped_data.get("GST Identification Number (GSTIN)") or ""
    gst_treatment = mapped_data.get("GST Treatment", "")
    if gst_treatment == "business_gst" and (
        not gstin or not _GSTIN_RE.match(gstin.strip().upper())
    ):
        score -= 0.20

    # Penalize for suspicious invoice number
    inv_num = str(mapped_data.get("Invoice Number") or "")
    if not inv_num or inv_num.startswith("::") or inv_num.isdigit():
        score -= 0.15

    # Penalize for missing customer
    if not mapped_data.get("Customer Name"):
        score -= 0.10

    # Penalize for LLM warnings that survived retries
    if mapped_data.get("_math_warnings"):
        score -= 0.15

    return round(max(0.0, min(1.0, score)), 2)
