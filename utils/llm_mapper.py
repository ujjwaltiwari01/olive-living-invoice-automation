"""
LLM Invoice Mapper (Layers 2 & 3)

Sends Document AI output to GPT-4o for schema mapping.
Key improvements:
  L2: Expanded system prompt with math constraint, GSTIN validation, freight/discount rules
  L3: Self-healing retry loop — if numbers don't add up, sends error back to GPT-4o to self-correct
"""

import os
import json
import math
import logging
from typing import Optional
from openai import OpenAI
from dotenv import load_dotenv

from utils.zoho_schema import ZohoInvoiceSchema
from utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)
client = OpenAI()

# ─── L2: Expanded System Prompt ──────────────────────────────────────────────
SYSTEM_PROMPT = """
You are a principal Indian tax accountant and data extraction engine.
Your job is to perfectly map raw OCR data from vendor invoices into the strict Zoho Books schema.

You will receive semi-structured JSON extracted by Google Document AI, including a `raw_text` field
containing the full page text. Always cross-verify entities against raw_text.

═══════════════════════════════════════════════════════════════
 RULE 1 — ENTITY IDENTIFICATION (VENDOR vs CUSTOMER) [NEW]
═══════════════════════════════════════════════════════════════
- These are incoming invoices/bills. **"Olive" (or Olive by Embassy, Olive Living) is the RECIPIENT.**
- You MUST extract the **SUPPLIER (Seller/Vendor)** as the primary entity in "Customer Name".
- Extract the **SUPPLIER'S GSTIN** in "GST Identification Number (GSTIN)". 
- IGNORE Olive's name and GSTIN (starting with 29AA...) for these fields.
- GST Treatment applies to the supplier (business_gst, business_none, etc.)

═══════════════════════════════════════════════════════════════
 RULE 2 — SUPPLIER GSTIN VALIDATION [CRITICAL]
═══════════════════════════════════════════════════════════════
A valid Indian GSTIN is EXACTLY 15 characters matching: ##AAAAA####A#Z#
- You MUST find the GSTIN belonging to the **Supplier/Vendor** (usually at the top).
- NEVER extract the GSTIN of the recipient (Olive).
- If the identified Supplier GSTIN is truncated, search `raw_text` for a valid 15-char replacement.
- NEVER output an invalid/truncated GSTIN.

═══════════════════════════════════════════════════════════════
 RULE 3 — LINE ITEM RATE EXTRACTION [MOST CRITICAL]
═══════════════════════════════════════════════════════════════
After extracting all line items, you MUST compute:
  computed_subtotal = sum(Quantity * Item_Price for each item)

If computed_subtotal differs from the apparent subtotal by more than 5%:
  → Go back to raw_text and re-extract each line item's rate individually
  → NEVER output Item_Price = 0 unless the invoice explicitly shows "0.00" or "Free"
  → If a rate column value is ambiguous, derive it: rate = line_amount / quantity
  → For textile/commodity invoices with "qty × rate = amount" columns, look for the "rate" column explicitly

═══════════════════════════════════════════════════════════════
 RULE 4 — TAX HANDLING [CRITICAL]
═══════════════════════════════════════════════════════════════
- CGST + SGST → ALWAYS SUM them into a single percentage (e.g., 9% + 9% = 18%).
- **Rule 4-B: Tax Summary Lookup**: If the main table lacks tax columns, look for a "Tax Summary" or "GST Summary" table at the bottom.
  → Every row in that summary table is indexed by HSN or Taxable Value.
  → Map the HSN from each line item to the Rate in the summary table.
  → If multiple items share an HSN, they MUST all have the same GST rate from the summary.
- NEVER assume a flat tax rate. If the summary table shows 5% for some HSNs and 18% for others, you MUST reflect this in the individual line items.
- Set Item Tax Type to "Tax Group". Tax Inclusive (true/false) based on whether Subtotal + Tax = Total.

═══════════════════════════════════════════════════════════════
 RULE 5 — TOTAL AMOUNT, TAX AMOUNT & OVERHEADS [CRITICAL]
═══════════════════════════════════════════════════════════════
Document AI often misidentifies the subtotal as total_amount. YOU MUST use raw_text
to find the true "Grand Total / Total Invoice Value / Net Amount Payable".

TAX AMOUNT: You MUST sum all tax components. If the footer has separate rows for
"CGST 9%" and "SGST 9%", the tax_amount must be the SUM (e.g., 768.6 + 768.6 = 1537.2).
NEVER just pick one row's value.

Before finalizing total_amount, scan raw_text for:
  "Freight", "Shipping", "Packing", "Handling", "Discount", "Round Off", "TCS", "TDS"
If found:
  → Extract exact amounts
  → The formula MUST hold: subtotal + freight - discount + TCS - TDS ± round_off = total_amount
  → Include freight in a separate "Adjustment" field if no explicit freight line item exists

Indian numbers: "1,60,760" = 160760.0 (lakh format). Never confuse commas with decimals.

═══════════════════════════════════════════════════════════════
 RULE 6 — SUPPLY TYPE & HSN/SAC
═══════════════════════════════════════════════════════════════
- Room charges, consultations, hotel stays, professional fees, software → "service"
- Goods, medicines, physical products, equipment → "goods"
- HSN = 4/6/8 digit code for goods; SAC = 6 digit code for services
- Extract exact code from line description if visible

═══════════════════════════════════════════════════════════════
 RULE 7 — FIELD DEFAULTS
═══════════════════════════════════════════════════════════════
- Always extract Invoice Number exactly as printed.
- **Customer Name = The Vendor/Supplier/Seller.** (Never Use Olive).
- If Due Date is missing, default to Invoice Date.
- Never hallucinate data. If a field cannot be found in raw_text, use null.
"""


# ─── L3: Math Verification ───────────────────────────────────────────────────
def _compute_subtotal(mapped_data: dict) -> float:
    """Sum qty * rate across all line items."""
    total = 0.0
    for item in mapped_data.get("line_items", []):
        qty = float(item.get("Quantity") or 0)
        rate = float(item.get("Item Price") or 0)
        total += qty * rate
    return round(total, 2)


def _get_avg_tax_rate(mapped_data: dict) -> float:
    """Get representative tax rate from line items for math check."""
    rates = [
        float(i.get("Item Tax %") or 0)
        for i in mapped_data.get("line_items", [])
        if (i.get("Item Tax %") or 0) > 0
    ]
    return (sum(rates) / len(rates) / 100) if rates else 0.0


def math_verify(mapped_data: dict) -> list:
    """
    L3: Checks that line item data is internally consistent with declared total.
    Returns a list of error strings, empty if all checks pass.
    """
    errors = []

    line_items = mapped_data.get("line_items", [])
    if not line_items:
        return ["No line items found."]

    declared_total = float(mapped_data.get("total_amount") or 0)

    # Check 1: Zero-rate items (almost always a data error)
    zero_rate_items = [
        i.get("Item Name", f"item[{idx}]")
        for idx, i in enumerate(line_items)
        if (i.get("Item Price") or 0) == 0
    ]
    if zero_rate_items:
        errors.append(
            f"Items with Item Price=0 found: {zero_rate_items}. "
            f"These are almost certainly extraction errors — re-read raw_text for the actual rate."
        )

    # Check 2: Math consistency
    if declared_total > 0:
        computed_sub = _compute_subtotal(mapped_data)
        avg_tax = _get_avg_tax_rate(mapped_data)

        # Check if inclusive tax (rate already includes tax)
        is_inclusive = any(
            i.get("Is Inclusive Tax") for i in line_items
        )

        computed_with_tax = computed_sub if is_inclusive else computed_sub * (1 + avg_tax)

        if computed_sub > 0:
            deviation = abs(computed_with_tax - declared_total) / declared_total
            if deviation > 0.08:  # Allow 8% tolerance for freight/rounding
                errors.append(
                    f"Math mismatch: sum(qty*rate)={computed_sub:.2f}, "
                    f"with_tax={computed_with_tax:.2f}, "
                    f"declared_total={declared_total:.2f} "
                    f"({deviation*100:.1f}% off). "
                    f"Re-examine raw_text and correct line item rates/quantities. "
                    f"Do NOT change total_amount — fix the line items."
                )

        # Check 2b: Tax consistency [TIGHTENED & MULTI-RATE AWARE]
        declared_tax = float(mapped_data.get("tax_amount") or 0)
        computed_tax = 0.0
        if not is_inclusive:
            computed_tax = sum((float(i.get("Quantity") or 0) * float(i.get("Item Price") or 0) * float(i.get("Item Tax %") or 0) / 100) for i in line_items)
        
        if declared_tax > 0:
            tax_deviation = abs(declared_tax - computed_tax)
            if tax_deviation > 2.0: # Allow 2 rupee rounding
                # Detect if the AI hallucinated a flat rate (e.g. all 18% when some are 5%)
                rates_used = set(float(i.get("Item Tax %") or 0) for i in line_items if float(i.get("Item Tax %") or 0) > 0)
                flat_rate_hint = ""
                if len(rates_used) == 1:
                    flat_rate_hint = (
                        f" (Note: You applied a flat {list(rates_used)[0]}% to all items. "
                        "This invoice likely has MIXED rates, e.g., some items at 5% and some at 18%. "
                        "Cross-reference the HSN/SAC code of each item with the 'Tax Summary' table at the bottom "
                        "to find the correct rate for each row.)"
                    )
                
                errors.append(
                    f"Tax mismatch: Top-level tax_amount={declared_tax:.2f} does not match "
                    f"sum of line item taxes={computed_tax:.2f}.{flat_rate_hint} "
                    f"Correct the Item Tax % for each line item using the footer summary."
                )

    # Check 3: Quantity=0 items
    zero_qty_items = [
        i.get("Item Name", f"item[{idx}]")
        for idx, i in enumerate(line_items)
        if (i.get("Quantity") or 0) == 0
    ]
    if zero_qty_items:
        errors.append(
            f"Items with Quantity=0: {zero_qty_items}. "
            f"Extract the actual quantity from raw_text."
        )

    return errors


# ─── Core LLM call ───────────────────────────────────────────────────────────
def _call_llm(doc_ai_output: dict, correction_context: Optional[str] = None) -> dict:
    """Single LLM call. If correction_context provided, appends it as a correction instruction."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    if correction_context:
        # Two-turn: original input + correction request
        messages.append({
            "role": "user",
            "content": json.dumps(doc_ai_output, indent=2, ensure_ascii=False)
        })
        messages.append({
            "role": "assistant",
            "content": "[Previous extraction was returned with math errors — correcting now]"
        })
        messages.append({
            "role": "user",
            "content": (
                "Your previous extraction had the following errors:\n\n"
                + correction_context
                + "\n\nPlease re-examine the raw_text field carefully and produce a corrected extraction. "
                "Focus especially on line item rates and quantities."
            )
        })
    else:
        # L2: Send structured hint alongside the raw entity data
        hint = {
            "declared_total_from_ocr": doc_ai_output.get("total_amount"),
            "declared_tax_from_ocr": doc_ai_output.get("tax_amount"),
            "ocr_line_item_count": len(doc_ai_output.get("line_items", [])),
            "gstin_valid": doc_ai_output.get("gstin_valid"),
            "gstin_raw": doc_ai_output.get("gstin"),
            "instruction": (
                "Use 'declared_total_from_ocr' as your anchor for total_amount. "
                "If gstin_valid=false, search raw_text for a valid 15-char GSTIN. "
                "Ensure sum(qty×rate) is consistent with the declared total."
            )
        }
        user_payload = {
            "ocr_entities": doc_ai_output,
            "extraction_hints": hint,
        }
        messages.append({
            "role": "user",
            "content": json.dumps(user_payload, indent=2, ensure_ascii=False)
        })

    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=messages,
        response_format=ZohoInvoiceSchema,
        temperature=0.0,
    )
    parsed = response.choices[0].message.parsed
    return parsed.model_dump(by_alias=True)


# ─── L3: Self-Healing Retry Entry Point ──────────────────────────────────────
def map_invoice_via_llm(doc_ai_output: dict, max_retries: int = 2) -> dict:
    """
    Maps Document AI output to Zoho schema with self-healing retry.

    Pipeline:
      1. Initial LLM extraction (with structured hint)
      2. Math verification
      3. If errors → send correction request to LLM (up to max_retries times)
      4. Return best result

    Args:
        doc_ai_output: Dict from extract_entities()
        max_retries:   Number of correction passes (default: 2)

    Returns:
        Mapped invoice dict matching ZohoInvoiceSchema, or {"error": ..., "Mapping Failed": True}
    """
    invoice_id = doc_ai_output.get("invoice_id", "UNKNOWN")
    logger.info(f"LLM_MAP_START: invoice '{invoice_id}' (max_retries={max_retries})")

    try:
        # ── Pass 1: Initial extraction ────────────────────────────────
        result = _call_llm(doc_ai_output)
        errors = math_verify(result)

        if not errors:
            logger.info(f"LLM_MAP_PASS1_OK: invoice '{invoice_id}' — math check passed")
            return result

        logger.warning(
            f"LLM_MAP_PASS1_ERRORS: invoice '{invoice_id}' — "
            f"{len(errors)} issue(s):\n" + "\n".join(f"  • {e}" for e in errors)
        )

        # ── Retry passes ──────────────────────────────────────────────
        for attempt in range(1, max_retries + 1):
            logger.info(f"LLM_MAP_RETRY_{attempt}: invoice '{invoice_id}'")
            correction_context = "\n".join(f"• {e}" for e in errors)

            try:
                result = _call_llm(doc_ai_output, correction_context=correction_context)
                errors = math_verify(result)

                if not errors:
                    logger.info(
                        f"LLM_MAP_RETRY_{attempt}_OK: invoice '{invoice_id}' — "
                        f"math check passed after correction"
                    )
                    return result

                logger.warning(
                    f"LLM_MAP_RETRY_{attempt}_STILL_ERRORS: invoice '{invoice_id}' — "
                    f"{len(errors)} issue(s) remain"
                )
            except Exception as retry_err:
                logger.error(f"LLM_MAP_RETRY_{attempt}_EXCEPTION: {retry_err}")
                break

        # ── Exhausted retries — return best effort ────────────────────
        logger.warning(
            f"LLM_MAP_BEST_EFFORT: invoice '{invoice_id}' — "
            f"returning result after {max_retries} retries with remaining errors: {errors}"
        )
        # Tag the result so HITL knows it needs human attention
        result["_math_warnings"] = errors
        return result

    except Exception as e:
        logger.error(f"LLM_MAP_FAILED: invoice '{invoice_id}' — {e}")
        return {"error": str(e), "Mapping Failed": True}
