import re
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

def _clean_numeric(value: str) -> float:
    """
    Cleans up a string currency/numeric value and converts to float.
    Correctly handles standard and European number formats.
    """
    if not value:
        return 0.0
        
    val_str = str(value).strip()
    if not val_str:
        return 0.0
        
    # Remove obvious non-numeric crud except for minus, period, and comma
    clean_str = re.sub(r'[^\d.,-]', '', val_str)
    
    # Check for European format e.g., 1.234,56
    last_comma = clean_str.rfind(',')
    last_dot = clean_str.rfind('.')
    
    if last_comma > last_dot:
        # European format: replace dots (thousands) with empty, and comma (decimal) with dot
        clean_str = clean_str.replace('.', '').replace(',', '.')
    else:
        # Standard format: replace commas (thousands) with empty
        clean_str = clean_str.replace(',', '')
        
    # Final safety regex to ensure valid float parsing
    clean_str = re.sub(r'[^\d.-]', '', clean_str)
    
    try:
        if not clean_str:
            return 0.0
        return float(clean_str)
    except Exception as e:
        logger.warning(f"Failed to clean numeric value: {value}. Error: {e}")
        return 0.0


def _parse_date(date_str: str) -> str:
    """
    Attempts to normalize common OCR date formats into ISO (YYYY-MM-DD).
    Returns the original string if parsing fails heavily.
    """
    if not date_str:
        return ""
        
    date_str = date_str.strip()
    
    # Strip ordinal suffixes
    clean_date = re.sub(r'(?<=\d)(st|nd|rd|th)\b', '', date_str, flags=re.IGNORECASE)
    
    # Strip dots, commas, and excessive spaces commonly produced by OCR
    clean_date = clean_date.replace('.', ' ').replace(',', ' ')
    clean_date = ' '.join(clean_date.split())
    
    # Common formats extended
    formats = [
        "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", 
        "%b %d %Y", "%B %d %Y", "%d %b %Y", "%d %B %Y",
        "%d %m %Y", "%Y %m %d", "%d-%b-%Y", "%d-%B-%Y"
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(clean_date, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
            
    # Try against original uncleaned string just in case
    for fmt in [f for f in formats if "-" in f or "/" in f]:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
            
    # Fallback to original if unrecognizable
    return date_str


def normalize_ocr_data(ocr_data: dict) -> dict:
    """
    Standardize raw OCR output before mapping.
    Converts amounts to floats, dates to standard ISO, and handles nulls.
    """
    logger.info("Normalizing OCR data...")
    normalized = {}
    
    normalized["supplier_name"] = str(ocr_data.get("supplier_name") or "").strip()
    normalized["invoice_id"] = str(ocr_data.get("invoice_id") or "").strip()
    
    # Dates
    normalized["invoice_date"] = _parse_date(ocr_data.get("invoice_date"))
    normalized["due_date"] = _parse_date(ocr_data.get("due_date") or normalized["invoice_date"])
    
    # Amounts
    normalized["total_amount"] = _clean_numeric(ocr_data.get("total_amount"))
    normalized["tax_amount"] = _clean_numeric(ocr_data.get("tax_amount"))
    
    # Other metadata tracking (optional for future use but requested in schema)
    normalized["currency_code"] = str(ocr_data.get("currency_code") or "USD").upper()
    normalized["gstin"] = str(ocr_data.get("gstin") or "").strip()
    normalized["notes"] = str(ocr_data.get("notes") or "").strip()
    
    # Line items
    raw_lines = ocr_data.get("line_items") or []
    norm_lines = []
    
    for item in raw_lines:
        # In Task 2, lines were just strings representing the mention_text.
        # We'll normalize them by trying to extract basic details or returning defaults
        # that the user can edit in the human verification interface.
        
        # If it's a dict (advanced parser setup), handle it, otherwise mock schema for human edit
        if isinstance(item, dict):
            # Document AI properties typically drop the prefix when strictly parsed, or keep them. We check both.
            desc = str(item.get("description") or item.get("line_item/description") or "").strip()
            qty_raw = item.get("quantity") or item.get("line_item/quantity") or 1
            price_raw = item.get("unit_price") or item.get("line_item/unit_price") or 0
            
            qty = _clean_numeric(qty_raw)
            price = _clean_numeric(price_raw)
            
            # Some parsers return line_item/amount instead of unit_price
            amount_raw = item.get("amount") or item.get("line_item/amount") or 0
            amount = _clean_numeric(amount_raw)
            
            if price == 0 and qty > 0 and amount > 0:
                price = round(amount / qty, 2)

            tax_perc_raw = item.get("tax_percentage") or item.get("line_item/tax_percentage") or item.get("tax_rate") or 0
            tax_perc = _clean_numeric(tax_perc_raw)
            hsn_sac = str(item.get("hsn_sac") or "")
        else:
             # Fallback line text
            desc = str(item).strip()
            qty = 1.0
            price = 0.0
            tax_perc = 0.0
            hsn_sac = ""
            
        # Filter out spurious line items that Document AI sometimes catches (like Payment History or Totals)
        desc_lower = desc.lower()
        skip_keywords = [
            "mastercard", "visa", "amex", "discover", "american express",
            "payment method", "amount paid", "payment history", "previous balance", 
            "payment received", "subtotal", "total amount"
        ]
        
        if any(kw in desc_lower for kw in skip_keywords):
            logger.info(f"Filtered out spurious line item: {desc}")
            continue
            
        norm_lines.append({
            "Item Name": desc[:100] if desc else "Unknown Item",
            "Item Desc": desc,
            "Quantity": qty,
            "Item Price": price,
            "Item Tax %": tax_perc,
            "HSN/SAC": hsn_sac
        })
        
    normalized["line_items"] = norm_lines
    logger.info("OCR data normalized successfully.")
    
    return normalized


def map_to_zoho_schema(normalized_data: dict) -> dict:
    """
    Transforms the normalized dictionary strictly into the Zoho Books schema structure.
    """
    logger.info("Mapping normalized data to Zoho schema...")
    
    zoho_payload = {
        "Invoice Number": normalized_data["invoice_id"],
        "Invoice Date": normalized_data["invoice_date"],
        "Due Date": normalized_data["due_date"],
        "Customer Name": normalized_data["supplier_name"],
        "Currency Code": normalized_data["currency_code"],
        "GST Identification Number": normalized_data["gstin"],
        "Notes": normalized_data["notes"],
        "Total Amount": normalized_data["total_amount"],
        "Tax Amount": normalized_data["tax_amount"],
        "line_items": []
    }
    
    for item in normalized_data["line_items"]:
        # We explicitly map keys matching the target schema defined in Task 3
        mapped_item = {
            "Item Name": item.get("Item Name", ""),
            "Item Desc": item.get("Item Desc", ""),
            "Quantity": float(item.get("Quantity", 1.0)),
            "Item Price": float(item.get("Item Price", 0.0)),
            "Item Tax %": float(item.get("Item Tax %", 0.0)),
            "HSN/SAC": item.get("HSN/SAC", "")
        }
        zoho_payload["line_items"].append(mapped_item)
        
    logger.info("Zoho mapping completed.")
    return zoho_payload
