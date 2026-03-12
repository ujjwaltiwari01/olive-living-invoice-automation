"""
Zoho Books Schema Normalization Engine (Task 4)

Converts verified invoice payloads (human-readable aliases from the HITL interface)
into strict Zoho Books API-compliant payloads for the `create-an-invoice` endpoint.

Field mappings verified against Zoho Books OpenAPI spec (invoices.yml).
"""

import re
from typing import Dict, Any, List, Tuple, Optional
from utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Field Maps — verified against Zoho invoices.yml `create-an-invoice-request`
# ---------------------------------------------------------------------------

INVOICE_FIELD_MAP: Dict[str, str] = {
    "Invoice Number":                      "invoice_number",
    "Invoice Date":                        "date",
    "Due Date":                            "due_date",
    "Customer Name":                       "customer_name",
    "Currency Code":                       "currency_code",
    "Exchange Rate":                       "exchange_rate",
    "Notes":                               "notes",
    "Terms & Conditions":                  "terms",
    "GST Treatment":                       "gst_treatment",
    "GST Identification Number (GSTIN)":   "gst_no",
    "Place of Supply":                     "place_of_supply",
    "Payment Terms":                       "payment_terms_label",
    "Adjustment":                          "adjustment",
    "Adjustment Description":              "adjustment_description",
    "Shipping Charge":                     "shipping_charge",
    "Discount":                            "discount",
    "Is Discount Before Tax":              "is_discount_before_tax",
    "Discount Type":                       "discount_type",
    "Sales person":                        "salesperson_name",
}

LINE_ITEM_FIELD_MAP: Dict[str, str] = {
    "Item Name":       "name",
    "Item Desc":       "description",
    "Quantity":        "quantity",
    "Item Price":      "rate",
    "HSN/SAC":         "hsn_or_sac",
    "Item Tax %":      "tax_percentage",
    "Item Tax":        "tax_name",
    "Item Tax Type":   "tax_type",
    "Item Type":       "product_type",
    "Usage unit":      "unit",
    "Discount":        "discount",
    "Discount Amount": "discount_amount",
}

# Fields that exist in the verified payload but are NOT accepted by the
# Zoho create-invoice request schema.  Silently dropped.
FIELDS_TO_DROP = {
    # Not in request schema
    "Estimate Number", "Invoice Status",
    # TCS/TDS managed via separate Zoho APIs
    "TCS Tax Name", "TCS Percentage", "TCS Amount",
    "Nature Of Collection", "TCS Payable Account", "TCS Receivable Account",
    "TDS Name", "TDS Percentage", "TDS Amount", "TDS Section Code",
    # Line-item fields not in request schema
    "SKU", "Item Tax Exemption Reason",
    # Internal fields
    "total_amount", "tax_amount", "Bypass Math",
    # CSV fields not in API
    "Expense Reference ID", "PurchaseOrder",
    "Shipping Charge Tax Name", "Shipping Charge Tax Type",
    "Shipping Charge Tax %", "Shipping Charge Tax Exemption Code",
    "Shipping Charge SAC Code",
    "Reverse Charge Tax Name", "Reverse Charge Tax Rate", "Reverse Charge Tax Type",
    "Supply Type", "Entity Discount Percent", "Entity Discount Amount",
    "E-Commerce Operator Name", "E-Commerce Operator GSTIN",
    "PayPal", "Razorpay", "Partial Payments",
    "Template Name", "Account",
    "Branch Name", "Warehouse Name", "Expected Payment Date",
    "Project Name",
}

# Zoho auto-calculates these — sending them causes API rejection
CALCULATED_FIELDS = {
    "sub_total", "tax_total", "total", "balance",
    "payment_made", "credits_applied", "item_total",
}

# ---------------------------------------------------------------------------
# Date regex
# ---------------------------------------------------------------------------
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Payment Terms label → days lookup
_PAYMENT_TERMS_DAYS = {
    "due on receipt":   0,
    "net 7":            7,
    "net 10":          10,
    "net 15":          15,
    "net 30":          30,
    "net 45":          45,
    "net 60":          60,
    "net 90":          90,
}


# ===================================================================
# 1. normalize_invoice_schema
# ===================================================================
def normalize_invoice_schema(verified_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Takes the raw verified_payload from the HITL interface and returns
    a cleaned copy with safe defaults and type coercions applied.

    Does NOT rename keys — that is handled by map_invoice_fields().
    """
    data = verified_payload.copy()

    # --- Safe string defaults ---
    for key in ("Invoice Number", "Invoice Date", "Due Date", "Customer Name",
                "Currency Code", "Notes", "GST Treatment",
                "GST Identification Number (GSTIN)", "Place of Supply",
                "Payment Terms"):
        if data.get(key) is None:
            data[key] = ""

    # Currency default
    if not data.get("Currency Code"):
        data["Currency Code"] = "INR"

    # Exchange Rate default
    try:
        data["Exchange Rate"] = float(data.get("Exchange Rate", 1.0) or 1.0)
    except (ValueError, TypeError):
        data["Exchange Rate"] = 1.0

    # Due Date default → Invoice Date
    if not data.get("Due Date") and data.get("Invoice Date"):
        data["Due Date"] = data["Invoice Date"]

    # Normalize line_items list
    if "line_items" not in data or not isinstance(data.get("line_items"), list):
        data["line_items"] = []

    # Normalize each line item
    normalized_lines = []
    for item in data["line_items"]:
        if not isinstance(item, dict):
            continue
        norm = item.copy()

        # Name fallback
        if not norm.get("Item Name"):
            norm["Item Name"] = "Unnamed Item"

        # Numeric coercions
        for num_key in ("Quantity", "Item Price", "Item Tax %"):
            try:
                norm[num_key] = float(norm.get(num_key, 0) or 0)
            except (ValueError, TypeError):
                norm[num_key] = 0.0

        # Quantity minimum
        if norm["Quantity"] <= 0:
            norm["Quantity"] = 1.0

        # Boolean coercion
        norm["Is Inclusive Tax"] = bool(norm.get("Is Inclusive Tax", False))

        # product_type fix: "service" → "services" (Zoho uses plural)
        item_type = str(norm.get("Item Type", "services")).strip().lower()
        if item_type == "service":
            item_type = "services"
        elif item_type not in ("goods", "services"):
            item_type = "services"
        norm["Item Type"] = item_type

        normalized_lines.append(norm)

    data["line_items"] = normalized_lines
    return data


# ===================================================================
# 2. map_invoice_fields
# ===================================================================
def map_invoice_fields(normalized_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Renames top-level keys from human-readable aliases to Zoho API snake_case
    using INVOICE_FIELD_MAP.  Drops unknown/unsupported fields.
    """
    zoho = {}

    for our_key, zoho_key in INVOICE_FIELD_MAP.items():
        if our_key in normalized_data:
            val = normalized_data[our_key]
            if val is not None and val != "":
                zoho[zoho_key] = val

    # --- Special: is_inclusive_tax (invoice-level) ---
    # Promote from per-line-item boolean to invoice-level.
    # If ANY line item has Is Inclusive Tax = True, set invoice-level to True.
    line_items = normalized_data.get("line_items", [])
    any_inclusive = any(
        item.get("Is Inclusive Tax", False) for item in line_items
    )
    zoho["is_inclusive_tax"] = any_inclusive

    # --- Special: payment_terms (integer days) ---
    label = str(normalized_data.get("Payment Terms", "") or "").strip()
    if label:
        zoho["payment_terms_label"] = label
        days = _PAYMENT_TERMS_DAYS.get(label.lower())
        if days is not None:
            zoho["payment_terms"] = days
        else:
            # Try to extract a number from the label (e.g., "Net 20" → 20)
            match = re.search(r"\d+", label)
            if match:
                zoho["payment_terms"] = int(match.group())

    return zoho


# ===================================================================
# 3. map_line_items
# ===================================================================
def map_line_items(line_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Converts each line item dict from human-readable keys to Zoho API keys.
    Enforces types: rate → float, quantity → float, name → non-empty string.
    """
    zoho_items = []

    for item in line_items:
        zoho_item: Dict[str, Any] = {}

        for our_key, zoho_key in LINE_ITEM_FIELD_MAP.items():
            if our_key in item:
                val = item[our_key]
                if val is not None and val != "":
                    zoho_item[zoho_key] = val

        # Type enforcement
        if "rate" in zoho_item:
            try:
                zoho_item["rate"] = round(float(zoho_item["rate"]), 2)
            except (ValueError, TypeError):
                zoho_item["rate"] = 0.0

        if "quantity" in zoho_item:
            try:
                zoho_item["quantity"] = round(float(zoho_item["quantity"]), 2)
            except (ValueError, TypeError):
                zoho_item["quantity"] = 1.0

        if "tax_percentage" in zoho_item:
            try:
                zoho_item["tax_percentage"] = round(float(zoho_item["tax_percentage"]), 2)
            except (ValueError, TypeError):
                zoho_item.pop("tax_percentage", None)

        if "discount" in zoho_item:
            try:
                zoho_item["discount"] = round(float(zoho_item["discount"]), 2)
            except (ValueError, TypeError):
                zoho_item.pop("discount", None)

        if "discount_amount" in zoho_item:
            try:
                zoho_item["discount_amount"] = round(float(zoho_item["discount_amount"]), 2)
            except (ValueError, TypeError):
                zoho_item.pop("discount_amount", None)

        # Name must exist
        if not zoho_item.get("name"):
            zoho_item["name"] = "Unnamed Item"

        zoho_items.append(zoho_item)

    return zoho_items


# ===================================================================
# 4. remove_calculated_fields
# ===================================================================
def remove_calculated_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Strips all Zoho auto-calculated fields from the payload.
    Also strips any FIELDS_TO_DROP that leaked through.
    """
    cleaned = {}
    for key, val in payload.items():
        if key in CALCULATED_FIELDS:
            logger.debug(f"Stripped calculated field: {key}")
            continue
        if key in FIELDS_TO_DROP:
            logger.debug(f"Stripped unsupported field: {key}")
            continue
        cleaned[key] = val
    return cleaned


# ===================================================================
# 5. resolve_customer_id
# ===================================================================
def resolve_customer_id(customer_name: Optional[str]) -> Dict[str, Any]:
    """
    Resolves a customer name to a Zoho Books customer_id.

    STUB: Returns a placeholder dict. When the Zoho API OAuth connection
    is configured, this will call the Zoho Contacts API:
        GET /contacts?contact_name={customer_name}

    Returns:
        dict with customer_id (or customer_name fallback) and resolution flag.
    """
    result = {
        "_requires_customer_id_resolution": True,
    }

    if customer_name and customer_name.strip():
        result["customer_name"] = customer_name.strip()
        logger.warning(
            f"customer_id resolution stubbed for '{customer_name}'. "
            f"Actual Zoho Contacts API lookup needed before API submission."
        )
    else:
        result["customer_name"] = "Unknown Customer"
        logger.error("No customer name provided for customer_id resolution.")

    return result


# ===================================================================
# 6. validate_invoice_payload
# ===================================================================
def validate_invoice_payload(payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Final validation gate before the payload can be sent to Zoho.

    Returns:
        (is_valid, list_of_error_messages)
    """
    errors: List[str] = []

    # --- Required: customer_name or customer_id ---
    if not payload.get("customer_id") and not payload.get("customer_name"):
        errors.append("Missing required field: customer_id or customer_name")

    # --- Required: line_items ---
    line_items = payload.get("line_items", [])
    if not line_items:
        errors.append("Invoice must have at least one line item")
    else:
        for i, item in enumerate(line_items):
            prefix = f"line_items[{i}]"

            if not item.get("name"):
                errors.append(f"{prefix}: Missing required field 'name'")

            rate = item.get("rate")
            if rate is None:
                errors.append(f"{prefix}: Missing required field 'rate'")
            elif not isinstance(rate, (int, float)):
                errors.append(f"{prefix}: 'rate' must be a number, got {type(rate).__name__}")

            qty = item.get("quantity")
            if qty is None:
                errors.append(f"{prefix}: Missing required field 'quantity'")
            elif not isinstance(qty, (int, float)):
                errors.append(f"{prefix}: 'quantity' must be a number, got {type(qty).__name__}")
            elif qty <= 0:
                errors.append(f"{prefix}: 'quantity' must be > 0, got {qty}")

    # --- Date format ---
    for date_field in ("date", "due_date"):
        val = payload.get(date_field)
        if val and not _DATE_RE.match(str(val)):
            errors.append(f"'{date_field}' must be yyyy-mm-dd format, got '{val}'")

    # --- Currency code ---
    currency = payload.get("currency_code")
    if currency and (not isinstance(currency, str) or len(currency) != 3):
        errors.append(f"'currency_code' must be 3-letter ISO code, got '{currency}'")

    # --- GST treatment values ---
    gst = payload.get("gst_treatment")
    valid_gst = {"business_gst", "business_none", "overseas", "consumer"}
    if gst and gst not in valid_gst:
        errors.append(f"'gst_treatment' must be one of {valid_gst}, got '{gst}'")

    # --- Exchange rate ---
    er = payload.get("exchange_rate")
    if er is not None:
        if not isinstance(er, (int, float)) or er <= 0:
            errors.append(f"'exchange_rate' must be a positive number, got '{er}'")

    # --- GST number format (Indian: 15 chars) ---
    gst_no = payload.get("gst_no")
    if gst_no and isinstance(gst_no, str) and gst_no.strip():
        if len(gst_no.strip()) != 15:
            errors.append(f"'gst_no' must be 15 characters, got {len(gst_no.strip())}")

    is_valid = len(errors) == 0

    if not is_valid:
        logger.warning(f"Payload validation failed with {len(errors)} error(s): {errors}")
    else:
        logger.info("Payload validation passed.")

    return is_valid, errors


# ===================================================================
# 7. build_zoho_payload  — Master Pipeline
# ===================================================================
def build_zoho_payload(verified_payload: Dict[str, Any]) -> Tuple[Dict[str, Any], bool, List[str]]:
    """
    Master pipeline: converts a verified invoice payload into a Zoho
    Books API-compliant dict ready for the create-invoice endpoint.

    Pipeline:
        normalize → map_invoice_fields + map_line_items → resolve_customer_id
        → remove_calculated_fields → validate

    Args:
        verified_payload: The dict from the HITL verification interface.

    Returns:
        (zoho_payload, is_valid, validation_errors)
    """
    logger.info(f"Building Zoho payload for invoice: {verified_payload.get('Invoice Number', 'UNKNOWN')}")

    # Step 1: Normalize
    normalized = normalize_invoice_schema(verified_payload)

    # Step 2: Map invoice-level fields
    zoho_payload = map_invoice_fields(normalized)

    # Step 3: Map line items
    zoho_payload["line_items"] = map_line_items(normalized.get("line_items", []))

    # Step 4: Resolve customer ID
    customer_info = resolve_customer_id(normalized.get("Customer Name"))
    zoho_payload.update(customer_info)

    # Step 5: Remove calculated fields (safety pass on final payload)
    zoho_payload = remove_calculated_fields(zoho_payload)

    # Step 6: Validate
    is_valid, errors = validate_invoice_payload(zoho_payload)

    if is_valid:
        logger.info(f"Zoho payload ready for invoice: {zoho_payload.get('invoice_number', 'N/A')}")
    else:
        logger.error(f"Zoho payload INVALID for invoice: {zoho_payload.get('invoice_number', 'N/A')}")

    return zoho_payload, is_valid, errors
