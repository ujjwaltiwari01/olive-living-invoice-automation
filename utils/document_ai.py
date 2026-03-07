import os
import time
import io
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


def extract_entities(document: documentai.Document) -> dict:
    """
    Parses Document AI entities such as supplier_name, total_amount, etc.
    Returns a normalized Python dictionary.
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
        "line_items": []
    }
    
    if not hasattr(document, 'entities'):
        return data

    for entity in document.entities:
        key = entity.type_
        val = entity.mention_text or ""
        
        # Override with highly accurate normalized value if available
        if hasattr(entity, 'normalized_value') and entity.normalized_value:
            if hasattr(entity.normalized_value, 'text') and entity.normalized_value.text:
                val = entity.normalized_value.text
        
        if key == "supplier_name":
            data["supplier_name"] = val
        elif key == "invoice_id":
            data["invoice_id"] = val
        elif key == "invoice_date":
            # Just grabbing text, parsing datetime can be complex
            data["invoice_date"] = val
        elif key == "total_amount":
            data["total_amount"] = val
        elif key == "total_tax_amount":
            data["tax_amount"] = val
        elif key == "due_date":
            data["due_date"] = val
        elif key == "currency":
            data["currency_code"] = val
        elif key == "supplier_tax_id" or key == "receiver_tax_id":
            data["gstin"] = val
        elif key == "line_item":
            # Extract sub-entities (properties) into a dictionary
            line_dict = {}
            if hasattr(entity, 'properties') and entity.properties:
                for prop in entity.properties:
                    # e.g., mapping line_item/description to description
                    prop_key = prop.type_.split('/')[-1]
                    prop_val = prop.mention_text or ""
                    
                    if hasattr(prop, 'normalized_value') and prop.normalized_value:
                        if hasattr(prop.normalized_value, 'text') and prop.normalized_value.text:
                            prop_val = prop.normalized_value.text
                            
                    if prop_key in line_dict and line_dict[prop_key]:
                        # Concatenate if already exists (avoids overwriting multi-line descriptions)
                        line_dict[prop_key] += " " + prop_val.replace('\n', ' ')
                    else:
                        line_dict[prop_key] = prop_val.replace('\n', ' ')
            else:
                line_dict["description"] = val.replace('\n', ' ')
                
            data["line_items"].append(line_dict)
            
    return data


def process_invoice(file_bytes: bytes, file_name: str, client: documentai.DocumentProcessorServiceClient, max_retries: int = 3) -> dict:
    """
    Sends the document to Document AI using exponential backoff retry.
    Returns the parsed entities as a dictionary or a dict with error status.
    """
    if not client:
        return {"status": "auth_error"}

    # Determine mime type by extension natively 
    ext = file_name.split(".")[-1].lower() if "." in file_name else ""
    mime_type = "application/pdf" if ext == "pdf" else "image/jpeg"
    
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
