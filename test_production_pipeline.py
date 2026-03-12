"""
Production-Level Pipeline Test Script

Processes all test invoices through the FULL pipeline:
  1. Document AI OCR extraction
  2. LLM (GPT-4o) schema mapping
  3. Financial validation
  4. Zoho Schema Transformation
  5. Final Zoho payload validation

Outputs a detailed report at each stage showing what passed/failed and why.
"""

import os
import sys
import json
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from google.cloud import documentai
from google.oauth2 import service_account

from utils.document_ai import extract_entities, process_invoice
from utils.llm_mapper import map_invoice_via_llm
from utils.financial_validation import validate_financial_rules
from utils.zoho_schema_transformer import (
    normalize_invoice_schema,
    map_invoice_fields,
    map_line_items,
    remove_calculated_fields,
    resolve_customer_id,
    validate_invoice_payload,
    build_zoho_payload,
)

# ─── Config ───────────────────────────────────────────────────────────
TEST_DIR = r"d:\Olive invoice automation\test invoice"
OUTPUT_DIR = r"d:\Olive invoice automation\test_results"
CREDENTIALS_PATH = r"D:\Olive invoice automation\olive-invoice-automation-a4c87dd56907.json"
PROJECT_ID = "olive-invoice-automation"
LOCATION = "us"
PROCESSOR_ID = "b6c8916bc52a549"
# ──────────────────────────────────────────────────────────────────────

def get_raw_client():
    """Create Document AI client without Streamlit cache."""
    credentials = service_account.Credentials.from_service_account_file(CREDENTIALS_PATH)
    return documentai.DocumentProcessorServiceClient(credentials=credentials)



def stage_banner(stage_num, title, invoice_name):
    print(f"\n{'='*70}")
    print(f"  STAGE {stage_num}: {title}")
    print(f"  Invoice: {invoice_name}")
    print(f"{'='*70}")


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def test_single_invoice(filepath: str, idx: int, client) -> dict:
    """Process a single invoice through all 5 stages and collect results."""
    filename = os.path.basename(filepath)
    result = {
        "index": idx,
        "filename": filename,
        "stages": {},
        "final_status": "UNKNOWN",
    }
    
    print(f"\n{'#'*70}")
    print(f"  INVOICE {idx+1}: {filename}")
    print(f"{'#'*70}")
    
    # ── STAGE 1: Document AI OCR ──────────────────────────────
    stage_banner(1, "Document AI OCR Extraction", filename)
    try:
        with open(filepath, "rb") as f:
            file_bytes = f.read()
        
        raw_data = process_invoice(file_bytes, filename, client)
        
        if raw_data and raw_data.get("status") not in ("ocr_failed", "auth_error"):
            line_item_count = len(raw_data.get("line_items", []))
            has_raw_text = bool(raw_data.get("raw_text"))
            print(f"  ✅ OCR SUCCESS")
            print(f"     Line items extracted: {line_item_count}")
            print(f"     Raw text captured: {has_raw_text}")
            print(f"     Supplier: {raw_data.get('supplier_name', 'N/A')}")
            print(f"     Total: {raw_data.get('total_amount', 'N/A')}")
            result["stages"]["1_ocr"] = {"status": "PASS", "line_items": line_item_count}
        else:
            print(f"  ❌ OCR FAILED: {raw_data.get('status', 'Unknown error')}")
            result["stages"]["1_ocr"] = {"status": "FAIL", "error": str(raw_data.get("status", ""))}
            result["final_status"] = "FAILED_AT_OCR"
            return result
    except Exception as e:
        print(f"  ❌ OCR EXCEPTION: {str(e)}")
        result["stages"]["1_ocr"] = {"status": "EXCEPTION", "error": str(e)}
        result["final_status"] = "FAILED_AT_OCR"
        return result
    
    # ── STAGE 2: LLM Schema Mapping ──────────────────────────
    stage_banner(2, "LLM (GPT-4o) Schema Mapping", filename)
    try:
        mapped_data = map_invoice_via_llm(raw_data)
        
        if mapped_data.get("Mapping Failed"):
            print(f"  ❌ LLM MAPPING FAILED: {mapped_data.get('error', 'Unknown')}")
            result["stages"]["2_llm"] = {"status": "FAIL", "error": str(mapped_data.get("error", ""))}
            result["final_status"] = "FAILED_AT_LLM"
            return result
        
        inv_num = mapped_data.get("Invoice Number", "N/A")
        cust_name = mapped_data.get("Customer Name", "N/A")
        line_count = len(mapped_data.get("line_items", []))
        total = mapped_data.get("total_amount", "N/A")
        
        print(f"  ✅ LLM MAPPING SUCCESS")
        print(f"     Invoice #: {inv_num}")
        print(f"     Customer:  {cust_name}")
        print(f"     Line items: {line_count}")
        print(f"     Total:     {total}")
        print(f"     GST:       {mapped_data.get('GST Treatment', 'N/A')}")
        print(f"     GSTIN:     {mapped_data.get('GST Identification Number (GSTIN)', 'N/A')}")
        
        result["stages"]["2_llm"] = {
            "status": "PASS",
            "invoice_number": inv_num,
            "customer": cust_name,
            "line_items": line_count,
            "total": total,
        }
    except Exception as e:
        print(f"  ❌ LLM EXCEPTION: {str(e)}")
        result["stages"]["2_llm"] = {"status": "EXCEPTION", "error": str(e)}
        result["final_status"] = "FAILED_AT_LLM"
        return result
    
    # ── STAGE 3: Financial Validation ────────────────────────
    stage_banner(3, "Financial Validation Rules", filename)
    try:
        fin_errors = validate_financial_rules(mapped_data)
        
        if fin_errors:
            print(f"  ⚠️  FINANCIAL WARNINGS ({len(fin_errors)}):")
            for err in fin_errors:
                print(f"     • {err}")
            result["stages"]["3_financial"] = {"status": "WARNINGS", "errors": fin_errors}
        else:
            print(f"  ✅ FINANCIAL VALIDATION PASSED (0 warnings)")
            result["stages"]["3_financial"] = {"status": "PASS", "errors": []}
    except Exception as e:
        print(f"  ❌ FINANCIAL VALIDATION EXCEPTION: {str(e)}")
        result["stages"]["3_financial"] = {"status": "EXCEPTION", "error": str(e)}
        # Don't stop — financial warnings are not blockers
    
    # ── STAGE 4: Zoho Schema Transformation ──────────────────
    stage_banner(4, "Zoho Schema Transformation", filename)
    try:
        zoho_payload, is_valid, zoho_errors = build_zoho_payload(mapped_data)
        
        if is_valid:
            print(f"  ✅ ZOHO TRANSFORMATION PASSED")
            result["stages"]["4_zoho_transform"] = {"status": "PASS"}
        else:
            print(f"  ❌ ZOHO TRANSFORMATION FAILED ({len(zoho_errors)} errors):")
            for err in zoho_errors:
                print(f"     • {err}")
            result["stages"]["4_zoho_transform"] = {"status": "FAIL", "errors": zoho_errors}
            result["final_status"] = "FAILED_AT_ZOHO_VALIDATION"
    except Exception as e:
        print(f"  ❌ ZOHO TRANSFORMATION EXCEPTION: {str(e)}")
        result["stages"]["4_zoho_transform"] = {"status": "EXCEPTION", "error": str(e)}
        result["final_status"] = "FAILED_AT_ZOHO_TRANSFORM"
        return result
    
    # ── STAGE 5: Final Zoho Payload Audit ─────────────────────
    stage_banner(5, "Final Zoho Payload Audit", filename)
    
    # Check for forbidden fields
    forbidden = {"sub_total", "tax_total", "total", "balance", "payment_made",
                 "credits_applied", "item_total", "total_amount", "tax_amount",
                 "Bypass Math", "Invoice Status", "Estimate Number",
                 "TCS Amount", "TDS Amount", "SKU"}
    leaked = [k for k in zoho_payload.keys() if k in forbidden]
    
    # Check required structure
    has_line_items = bool(zoho_payload.get("line_items"))
    has_customer = bool(zoho_payload.get("customer_name") or zoho_payload.get("customer_id"))
    has_date = bool(zoho_payload.get("date"))
    
    # Check line item completeness
    item_issues = []
    for i, item in enumerate(zoho_payload.get("line_items", [])):
        if not item.get("name"):
            item_issues.append(f"  line_items[{i}]: missing 'name'")
        if item.get("rate") is None:
            item_issues.append(f"  line_items[{i}]: missing 'rate'")
        if item.get("quantity") is None:
            item_issues.append(f"  line_items[{i}]: missing 'quantity'")
        if not isinstance(item.get("rate", 0), (int, float)):
            item_issues.append(f"  line_items[{i}]: 'rate' is {type(item.get('rate')).__name__}, expected number")
        if not isinstance(item.get("quantity", 0), (int, float)):
            item_issues.append(f"  line_items[{i}]: 'quantity' is {type(item.get('quantity')).__name__}, expected number")
    
    audit_pass = True
    
    if leaked:
        print(f"  ❌ LEAKED FORBIDDEN FIELDS: {leaked}")
        audit_pass = False
    else:
        print(f"  ✅ No forbidden fields in payload")
    
    if not has_line_items:
        print(f"  ❌ MISSING line_items")
        audit_pass = False
    else:
        print(f"  ✅ line_items present ({len(zoho_payload['line_items'])} items)")
    
    if not has_customer:
        print(f"  ❌ MISSING customer identifier")
        audit_pass = False
    else:
        print(f"  ✅ customer present: {zoho_payload.get('customer_name', zoho_payload.get('customer_id'))}")
    
    if not has_date:
        print(f"  ❌ MISSING date")
        audit_pass = False
    else:
        print(f"  ✅ date: {zoho_payload.get('date')}")
    
    if item_issues:
        print(f"  ❌ LINE ITEM ISSUES:")
        for issue in item_issues:
            print(f"     {issue}")
        audit_pass = False
    else:
        print(f"  ✅ All line items have name/rate/quantity")
    
    result["stages"]["5_audit"] = {
        "status": "PASS" if audit_pass else "FAIL",
        "leaked_fields": leaked,
        "item_issues": item_issues,
    }
    
    # ── Save outputs ─────────────────────────────────────────
    safe_name = filename.replace(" ", "_").replace(".png", "").replace(".jpg", "")
    
    # Save LLM output
    with open(os.path.join(OUTPUT_DIR, f"{safe_name}_llm.json"), "w", encoding="utf-8") as f:
        json.dump(mapped_data, f, indent=2, ensure_ascii=False)
    
    # Save Zoho payload
    with open(os.path.join(OUTPUT_DIR, f"{safe_name}_zoho.json"), "w", encoding="utf-8") as f:
        json.dump(zoho_payload, f, indent=2, ensure_ascii=False)
    
    # Set final status
    if result["final_status"] == "UNKNOWN":
        if audit_pass and is_valid:
            result["final_status"] = "ALL_STAGES_PASSED"
        elif is_valid:
            result["final_status"] = "PASSED_WITH_AUDIT_WARNINGS"
        else:
            result["final_status"] = "FAILED_AT_ZOHO_VALIDATION"
    
    return result


def print_summary(results: list):
    """Print a final summary table."""
    print(f"\n\n{'='*70}")
    print(f"  PRODUCTION TEST SUMMARY — {len(results)} invoices")
    print(f"{'='*70}\n")
    
    passed = [r for r in results if r["final_status"] == "ALL_STAGES_PASSED"]
    warned = [r for r in results if "WARNING" in r["final_status"]]
    failed = [r for r in results if "FAIL" in r["final_status"]]
    
    print(f"  ✅ Fully Passed:  {len(passed)}/{len(results)}")
    print(f"  ⚠️  Warnings:     {len(warned)}/{len(results)}")
    print(f"  ❌ Failed:        {len(failed)}/{len(results)}")
    print()
    
    for r in results:
        icon = "✅" if r["final_status"] == "ALL_STAGES_PASSED" else "⚠️" if "WARNING" in r["final_status"] else "❌"
        print(f"  {icon} [{r['index']+1}] {r['filename']}")
        print(f"      Status: {r['final_status']}")
        
        for stage, data in r["stages"].items():
            s_icon = "✅" if data["status"] == "PASS" else "⚠️" if data["status"] == "WARNINGS" else "❌"
            extra = ""
            if data.get("errors"):
                extra = f" ({len(data['errors'])} issues)"
            if data.get("invoice_number"):
                extra = f" → {data['invoice_number']}"
            print(f"      {s_icon} {stage}: {data['status']}{extra}")
        print()
    
    if failed:
        print(f"\n{'─'*70}")
        print(f"  FAILURE DETAILS")
        print(f"{'─'*70}")
        for r in failed:
            print(f"\n  ❌ {r['filename']}:")
            for stage, data in r["stages"].items():
                if data["status"] in ("FAIL", "EXCEPTION"):
                    if data.get("errors"):
                        for err in data["errors"]:
                            print(f"     • {err}")
                    if data.get("error"):
                        print(f"     • {data['error']}")


def main():
    print(f"\n{'█'*70}")
    print(f"  OLIVE INVOICE AUTOMATION — PRODUCTION PIPELINE TEST")
    print(f"  Testing {len(os.listdir(TEST_DIR))} invoices through 5 stages")
    print(f"{'█'*70}")
    
    ensure_output_dir()
    
    # Create Document AI client ONCE (no Streamlit dependency)
    print(f"\n  Initializing Document AI client...")
    client = get_raw_client()
    print(f"  ✅ Client ready.\n")
    
    files = sorted([
        os.path.join(TEST_DIR, f)
        for f in os.listdir(TEST_DIR)
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".pdf"))
    ])
    
    print(f"  Found {len(files)} invoice files:")
    for i, f in enumerate(files):
        print(f"    [{i+1}] {os.path.basename(f)}")
    
    results = []
    start_time = time.time()
    
    for idx, filepath in enumerate(files):
        result = test_single_invoice(filepath, idx, client)
        results.append(result)
        print(f"\n  ⏱️  Time elapsed: {time.time() - start_time:.1f}s")
    
    # Save full results
    with open(os.path.join(OUTPUT_DIR, "test_report.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print_summary(results)
    
    total_time = time.time() - start_time
    print(f"\n  Total time: {total_time:.1f}s ({total_time/len(files):.1f}s per invoice)")
    print(f"  Full report saved to: {OUTPUT_DIR}\\test_report.json")
    print(f"  Individual outputs saved to: {OUTPUT_DIR}\\")


if __name__ == "__main__":
    main()
