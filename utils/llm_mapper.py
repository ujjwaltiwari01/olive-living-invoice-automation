import os
import json
from openai import OpenAI
from dotenv import load_dotenv

from utils.zoho_schema import ZohoInvoiceSchema
from utils.logger import get_logger

# Load environment variables (OPENAI_API_KEY)
load_dotenv()

logger = get_logger(__name__)

# Initialize OpenAI Client (expects OPENAI_API_KEY environment variable loaded from .env)
client = OpenAI()

SYSTEM_PROMPT = """
You are a principal Indian tax accountant and data extraction engine. 
Your job is to perfectly map raw OCR data from hospital, hotel, and vendor invoices into the strict 70-column Zoho Books schema.

You will receive semi-structured JSON extracted by Google Document AI. 
You must output a strictly defined JSON object matching the `ZohoInvoiceSchema`.

# CRITICAL INDIAN TAX & INVOICE RULES

1. **GST Treatment (`GST Treatment`)**
   - If a customer GSTIN is present: "business_gst"
   - If no customer GSTIN but the supplier is a hospital or hotel billing a patient/guest: "consumer"
   - If international (currency not INR): "overseas"
   - If inside an SEZ: "business_sez"

2. **Supply Types and HSN/SAC (`Item Type`, `HSN/SAC`)**
   - Hospital room charges, doctor consultations, hotel stays, professional fees, shipping: `Item Type` MUST be "service".
   - Medicines, physical goods, equipment: `Item Type` MUST be "goods".
   - Extract the 4, 6, or 8 digit HSN/SAC code if visible in the line description.

3. **Tax Handling (`Item Tax %`, `Item Tax Type`)**
   - Base tax percentage must be properly assigned to the line item.
   - If IGST is mentioned, apply it as total tax.
   - If CGST + SGST are mentioned, sum them up (e.g., 9% + 9% = 18%).
   - Set `Item Tax Type` to "Tax Group".
   - **Inclusive Tax (`Is Inclusive Tax`)**: If the invoice's unit `Rate/Price` or line `Amount` *already includes the tax* (i.e. Qty * Rate equals the final line amount AFTER tax), you MUST set `Is Inclusive Tax` to `true`. Otherwise, default to `false`.

4. **Total Invoice Value & Line Items Validation [CRITICAL]**
   - Document AI often misidentifies the subtotal as the `total_amount` entity and misses the Grand Total entirely. 
   - We are passing you the `raw_text` of the entire page alongside the entities. **YOU MUST** look at the `raw_text` to find the true "Total Invoice Value" (or "Grand Total") which includes all taxes. Use this real true total for the output `total_amount`.
   - You must similarly use the `raw_text` to verify the `tax_amount`. Do not blindly trust the parsed `tax_amount` entity if it only captures one line's CGST. Sum the CGST/SGST/IGST visible in the `raw_text` or derive it via `Grand Total - Subtotal`.
   - **TCS / TDS Overheads**: Scan the `raw_text` for Source Deductions (like "TCS 0.075 %" or "TDS"). If you see a TCS or TDS amount added or subtracted near the final totals (e.g., `24.00`), you MUST extract it into `TCS Amount` or `TDS Amount`.
   - **Indian Numbers**: Rupee values can be large (e.g., "160,760" is 1 Lakh 60 Thousand, i.e., 160760.0). Do not assume commas are decimals. Output exact raw integer/float totals.
   - Ensure you never include lines that are just payment summaries (e.g. "Amount Paid", "Visa", "Mastercard").

5. **Entity Relationships**
   - `Invoice Number`: Must be extracted exactly.
   - `Customer Name`: The entity or person being billed (Patient name, Guest name, or Company).

Always prefer data explicitly present in the OCR over hallucination. If a value like due-date is missing, default it to the invoice date.
"""

def map_invoice_via_llm(doc_ai_output: dict) -> dict:
    """
    Takes the initial normalized dictionary from Document AI and sends it to OpenAI
    for complex reasoning, tax derivation, and mapping into the Indian Zoho Schema.
    """
    logger.info(f"Sending invoice {doc_ai_output.get('invoice_id', 'UNKNOWN')} to LLM for Schema Mapping...")
    
    try:
        response = client.beta.chat.completions.parse(
            model="gpt-4o", # Recommended for complex JSON structuring
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(doc_ai_output, indent=2)}
            ],
            response_format=ZohoInvoiceSchema,
            temperature=0.0 # Deterministic
        )
        
        # Extract the structured Pydantic object and dump to dict
        strict_mapped_data = response.choices[0].message.parsed
        zoho_dict = strict_mapped_data.model_dump(by_alias=True)
        
        logger.info(f"Successfully mapped invoice via LLM.")
        return zoho_dict
        
    except Exception as e:
        logger.error(f"LLM Mapping failed for invoice {doc_ai_output.get('invoice_id', 'UNKNOWN')}. Error: {str(e)}")
        # In production we might raise, but here we'll fall back gracefully or return empty schema
        return {"error": str(e), "Mapping Failed": True}
