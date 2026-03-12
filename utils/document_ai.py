import os
import re
import time
import streamlit as st
from google.cloud import documentai
from google.oauth2 import service_account
from google.api_core import exceptions
from utils.logger import get_logger

logger = get_logger(__name__)

# Constants per requirements
PROJECT_ID = "olive-invoice-automation"
LOCATION = "us"
PROCESSOR_ID = "b6c8916bc52a549"
CREDENTIALS_PATH = r"D:\Olive invoice automation\olive-invoice-automation-a4c87dd56907.json"

# L1a: Correct MIME type map — PNG was incorrectly sent as image/jpeg
MIME_MAP = {
    "pdf":  "application/pdf",
    "png":  "image/png",
    "jpg":  "image/jpeg",
    "jpeg": "image/jpeg",
    "tiff": "image/tiff",
    "gif":  "image/gif",
    "bmp":  "image/bmp",
}

# L1b: Minimum confidence threshold — entities below this are unreliable
MIN_ENTITY_CONFIDENCE = 0.50

# L1c: GSTIN regex — exactly 15 chars, format: 2 digits + 5 alpha + 4 digits + 1 alpha + 1 alnum + Z + 1 alnum
GSTIN_RE = re.compile(r'^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]$')


@st.cache_resource(show_spinner="Initializing Document AI Client...")
def get_document_ai_client() -> documentai.DocumentProcessorServiceClient:
    """
    Initializes and caches the Google Document AI client.
    Because we process 100+ invoices, caching the client is mandatory for performance.
    """
    try:
        if not os.path.exists(CREDENTIALS_PATH):
            logger.error(f"Credentials not found at {CREDENTIALS_PATH}")
            st.error("Document AI authentication failed. Credentials file missing.")
            return None

        credentials = service_account.Credentials.from_service_account_file(CREDENTIALS_PATH)
        client = documentai.DocumentProcessorServiceClient(credentials=credentials)
        logger.info("Successfully initialized Document AI client.")
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Document AI client: {e}")
        st.error("Document AI authentication failed.")
        return None


def _sanitize_total_amount(val: str) -> str:
    """
    Heuristic specifically for total amounts. Document AI reads "160,76" as "160,760".
    If the string matches \d+,\d{3} but the last 1 or 2 chars are 0, it is extremely 
    likely to be a botched decimal (e.g. "160,760" -> 160.76).
    We only apply this to top-level totals to anchor the LLM.
    """
    if not val or not isinstance(val, str):
        return val
        
    import re
    
    # Match patterns like "160,760", "37,500" where the comma acts as a decimal
    if re.fullmatch(r'\d+,\d{2}0', val.strip()) or re.fullmatch(r'\d+,\d00', val.strip()):
        clean_num = val.strip().replace(',', '')
        try:
            return str(float(clean_num) / 1000.0)
        except ValueError:
            pass
            
    # Also catch "160,760" where it's 3 digits comma 3 digits: \d{1,3},\d{3}
    if re.fullmatch(r'\d{1,3},\d{3}', val.strip()) and val.strip().endswith('0'):
        clean_num = val.strip().replace(',', '')
        try:
            return str(float(clean_num) / 1000.0)
        except ValueError:
            pass
            
    return val

def extract_entities(document: documentai.Document) -> dict:
    """
    Parses Document AI entities with confidence filtering and GSTIN validation.
    
    L1b: Skips entities with confidence < MIN_ENTITY_CONFIDENCE.
    L1c: Validates GSTIN format and flags invalid GSTINs.
    """
    data = {
        "supplier_name": None,
        "invoice_id": None,
        "invoice_date": None,
        "total_amount": None,
        "tax_amount": None,
        "due_date": None,
        "currency_code": None,
        "gstin": None,
        "gstin_valid": None,
        "line_items": [],
        "raw_text": document.text if hasattr(document, 'text') else "",
        "entities": [],      # raw entity names for diagnostics
        "low_confidence_skipped": 0,
    }

    if not hasattr(document, 'entities'):
        return data

    for entity in document.entities:
        key = entity.type_
        confidence = getattr(entity, 'confidence', 1.0)

        # L1b: Skip low-confidence entities (except line_items — handled per-property)
        if key != "line_item" and confidence < MIN_ENTITY_CONFIDENCE:
            logger.warning(
                f"LOW_CONF_SKIP: entity '{key}' skipped (confidence={confidence:.2f} < {MIN_ENTITY_CONFIDENCE})"
            )
            data["low_confidence_skipped"] += 1
            continue

        data["entities"].append(key)
        val = entity.mention_text or ""

        # Prefer normalized value when available
        if hasattr(entity, 'normalized_value') and entity.normalized_value:
            if hasattr(entity.normalized_value, 'text') and entity.normalized_value.text:
                val = entity.normalized_value.text

        if key == "supplier_name":
            data["supplier_name"] = val
        elif key == "invoice_id":
            data["invoice_id"] = val
        elif key == "invoice_date":
            data["invoice_date"] = val
        elif key == "total_amount":
            data["total_amount"] = val
        elif key == "total_tax_amount":
            data["tax_amount"] = val
        elif key == "due_date":
            data["due_date"] = val
        elif key == "currency":
            data["currency_code"] = val
        elif key in ("supplier_tax_id", "receiver_tax_id"):
            # L1c: Validate GSTIN format before accepting
            candidate = val.strip().upper().replace(" ", "")
            if GSTIN_RE.match(candidate):
                data["gstin"] = candidate
                data["gstin_valid"] = True
                logger.info(f"GSTIN_VALID: {candidate} (confidence={confidence:.2f})")
            else:
                logger.warning(
                    f"GSTIN_INVALID: '{candidate}' does not match 15-char pattern. "
                    f"Storing raw but flagging for LLM correction."
                )
                data["gstin"] = candidate          # pass through — LLM will try to fix from raw_text
                data["gstin_valid"] = False
        elif key == "line_item":
            line_dict = {}
            if hasattr(entity, 'properties') and entity.properties:
                for prop in entity.properties:
                    prop_confidence = getattr(prop, 'confidence', 1.0)
                    prop_key = prop.type_.split('/')[-1]
                    prop_val = prop.mention_text or ""

                    if hasattr(prop, 'normalized_value') and prop.normalized_value:
                        if hasattr(prop.normalized_value, 'text') and prop.normalized_value.text:
                            prop_val = prop.normalized_value.text

                    # For line item properties, warn but don't skip (LLM can correct)
                    if prop_confidence < MIN_ENTITY_CONFIDENCE:
                        logger.warning(
                            f"LINE_ITEM_LOW_CONF: '{prop_key}'={prop_val!r} "
                            f"(confidence={prop_confidence:.2f})"
                        )

                    if prop_key in line_dict and line_dict[prop_key]:
                        line_dict[prop_key] += " " + prop_val.replace('\n', ' ')
                    else:
                        line_dict[prop_key] = prop_val.replace('\n', ' ')
            else:
                line_dict["description"] = val.replace('\n', ' ')

            data["line_items"].append(line_dict)

    # Anchor LLM by fixing top-level totals
    for key in ["total_amount", "tax_amount"]:
        if data.get(key):
            data[key] = _sanitize_total_amount(data[key])

    logger.info(
        f"ENTITIES_EXTRACTED: {len(data['entities'])} accepted, "
        f"{data['low_confidence_skipped']} skipped (low confidence), "
        f"{len(data['line_items'])} line_items, GSTIN_valid={data['gstin_valid']}"
    )
    return data


def process_invoice(file_bytes: bytes, file_name: str, client: documentai.DocumentProcessorServiceClient, max_retries: int = 3) -> dict:
    """
    Sends the document to Document AI using exponential backoff retry.
    Applies L4 image preprocessing before OCR for improved extraction accuracy.
    Returns the parsed entities as a dictionary or a dict with error status.
    """
    if not client:
        return {"status": "auth_error"}

    # L1a: Correct MIME type — PNG was previously sent as image/jpeg causing quality loss
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    mime_type = MIME_MAP.get(ext, "image/jpeg")

    # L4: Image preprocessing — deskew, contrast enhancement, upscale (images only)
    try:
        from utils.image_preprocessor import enhance_invoice_image, should_preprocess
        if should_preprocess(file_name):
            file_bytes, mime_type = enhance_invoice_image(file_bytes, file_name)
        else:
            logger.info(f"MIME_TYPE: {file_name} → {mime_type} (no preprocessing for PDFs)")
    except Exception as preproc_err:
        logger.warning(f"PREPROCESS_SKIP: {file_name} — {preproc_err}. Proceeding with original bytes.")

    logger.info(f"OCR_START: Processing {file_name} (mime={mime_type})")
    
    name = client.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)
    raw_document = documentai.RawDocument(content=file_bytes, mime_type=mime_type)
    request = documentai.ProcessRequest(name=name, raw_document=raw_document)

    logger.info(f"OCR_START: Processing {file_name}")

    for attempt in range(max_retries):
        try:
            # Synchronous call
            result = client.process_document(request=request)
            document = result.document
            
            logger.info(f"OCR_SUCCESS: {file_name} processed successfully.")
            return extract_entities(document)

        except (exceptions.ServiceUnavailable, exceptions.GatewayTimeout) as e:
            wait_time = 2 ** attempt
            logger.warning(f"API_ERROR: Timeout on {file_name}. Retrying in {wait_time}s... (Attempt {attempt+1}/{max_retries})")
            time.sleep(wait_time)
        except Exception as e:
            logger.error(f"OCR_FAILURE: Failed to process {file_name}. Error: {e}")
            return {"status": "ocr_failed"}
            
    # If we exhausted retries
    logger.error(f"OCR_FAILURE: Exhausted {max_retries} retries for {file_name}.")
    return {"status": "ocr_failed"}


def process_batch_invoices(files_info: list, progress_bar) -> list:
    """
    Accepts a list of dictionaries tracking uploaded files.
    Processes invoices sequentially and updates the state.
    Output: [{ "filename": "...", "status": "processed", "data": {...} }]
    """
    client = get_document_ai_client()
    results = []
    
    total = len(files_info)
    if total == 0:
        return results

    for idx, file_info in enumerate(files_info):
        filename = file_info["Invoice File Name"]
        file_bytes = file_info.get("bytes")
        
        # update UI
        progress = int(((idx + 1) / total) * 100)
        progress_bar.progress(progress, text=f"Processing invoice {idx + 1} of {total}: {filename}")

        if not file_bytes:
            logger.error(f"validation_error: Missing bytes for {filename}")
            file_info["Status"] = "ERROR"
            results.append({
                "filename": filename,
                "status": "validation_error",
                "data": {}
            })
            continue
            
        # Actual OCR API call
        data = process_invoice(file_bytes, filename, client)

        if data.get("status") == "ocr_failed":
            file_info["Status"] = "ERROR"
            results.append({
                "filename": filename,
                "status": "ocr_failed",
                "data": {}
            })
        elif data.get("status") == "auth_error":
            file_info["Status"] = "ERROR"
            results.append({
                "filename": filename,
                "status": "auth_error",
                "data": {}
            })
        else:
            file_info["Status"] = "OCR_COMPLETE"
            results.append({
                "filename": filename,
                "status": "processed",
                "data": data
            })
            
    return results
