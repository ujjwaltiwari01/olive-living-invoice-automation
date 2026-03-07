You are a **principal software architect specializing in enterprise financial automation systems, ERP integrations, and large-scale document processing pipelines with 20+ years of production experience**.

Your task is to implement **Task 3 of the Olive Invoice Automation Platform**.

This stage introduces a **human-in-the-loop verification layer** between the OCR extraction system and the Zoho Books API.

The system must convert **Google Document AI structured invoice output** into the **Zoho Books invoice schema**, present the data in a **high-integrity verification interface**, enforce **financial validation rules**, and produce a **clean, verified payload ready for ERP submission**.

The implementation must follow **production architecture standards**, support **high invoice throughput**, and guard against **common financial automation failures**.

---

# Existing System Context

The system currently contains:

### Task 1 – Invoice ingestion dashboard

Capabilities:
• Bulk invoice upload
• Camera capture preprocessing
• Validation of file types
• Upload tracking via session state

### Task 2 – OCR pipeline

Google Document AI Invoice Parser is already connected.

Configuration:

```id="h8ul0n"
Project ID: olive-invoice-automation
Processor ID: b6c8916bc52a549
Region: us
Credentials JSON:
D:\Olive invoice automation\olive-invoice-automation-a4c87dd56907.json
```

OCR output example:

```id="3b04o3"
{
 supplier_name
 invoice_id
 invoice_date
 total_amount
 tax_amount
 line_items
}
```

---

# Task 3 System Goal

Build a **financial verification subsystem** that performs:

1. OCR data normalization
2. Schema mapping to Zoho format
3. Deterministic validation checks
4. Human review interface
5. Payload preparation for ERP submission

The system must **never push raw OCR data into accounting systems**.

Instead it must enforce the following lifecycle:

```id="nghrcu"
OCR_COMPLETE
↓
MAPPED_TO_SCHEMA
↓
UNDER_REVIEW
↓
VERIFIED
↓
READY_FOR_ZOHO
```

---

# Zoho Invoice Schema

The system must support mapping to the Zoho Books invoice structure.

Important fields include:

```id="0mb3er"
Invoice Number
Estimate Number
Invoice Date
Invoice Status
Customer Name
GST Treatment
GST Identification Number
Place of Supply
PurchaseOrder
Payment Terms
Due Date
Expected Payment Date
Currency Code
Exchange Rate
Account
Item Name
SKU
Item Desc
Item Type
HSN/SAC
Quantity
Usage unit
Item Price
Item Tax
Item Tax Type
Item Tax %
Discount
Discount Amount
Adjustment
Adjustment Description
Notes
Terms & Conditions
Branch Name
Warehouse Name
```

Line items must be represented as nested objects.

---

# Architecture Requirements

Create a **dedicated transformation layer**.

New module:

```id="f0f7qj"
utils/zoho_mapper.py
```

Responsibilities:

• Transform OCR entities → Zoho schema
• Normalize date formats
• Normalize currency values
• Handle missing OCR fields
• Prepare structured payload

---

# Required Functions

## normalize_ocr_data()

Standardize OCR output before mapping.

Tasks:

• Convert date formats to ISO
• Convert numeric strings to floats
• Remove null values
• Normalize supplier naming

---

## map_to_zoho_schema()

Convert normalized OCR data to Zoho invoice schema.

Return structure:

```id="n8wr1p"
{
 "Invoice Number": "...",
 "Invoice Date": "...",
 "Customer Name": "...",
 "Currency Code": "INR",
 "line_items": [...]
}
```

Mapping must support multiple line items.

---

# Financial Validation Engine

Create validation module:

```id="41sgyo"
utils/financial_validation.py
```

Implement deterministic validation rules.

Mandatory fields:

```id="vwec1j"
Invoice Number
Invoice Date
Customer Name
At least one line item
Quantity
Item Price
```

Validation checks:

### Invoice Integrity

• invoice number must not be empty
• invoice number must be unique within session

---

### Amount Consistency

Verify:

```id="u4qf1d"
sum(line_items) == total_amount
```

Allow configurable tolerance (e.g. rounding differences).

---

### Date Validation

Ensure:

```id="ozc6t9"
Invoice Date ≤ Due Date
```

---

### GST Logic

If GST present:

```id="y8n0g8"
GSTIN must exist
Tax percentage must be valid
```

---

### Numeric Validation

Reject:

```id="ubqvte"
negative quantities
negative prices
non-numeric totals
```

---

# Human Verification Interface

Create new component:

```id="8tkfsb"
components/verification.py
```

The UI must allow finance staff to **review and correct OCR output**.

---

# UI Requirements

Use Streamlit forms:

```id="0mpph1"
st.form()
```

Editable fields include:

```id="9vgp6g"
Invoice Number
Invoice Date
Customer Name
GSTIN
Currency Code
Due Date
Notes
```

---

# Line Item Editing

Each invoice may contain multiple line items.

Provide UI controls for:

```id="ehd0un"
Item Name
Quantity
Unit Price
Tax %
HSN/SAC
```

Allow:

• Add line item
• Delete line item
• Modify existing values

---

# Verification Workflow

Provide actions:

```id="rslb24"
Approve Invoice
Reject Invoice
Flag for Review
```

Behavior:

Approve:

```id="tsnm4b"
status = VERIFIED
```

Reject:

```id="fl0kpa"
status = REJECTED
```

Flag:

```id="v7h6a7"
status = NEEDS_ATTENTION
```

---

# Batch Verification

The system must support reviewing invoices sequentially.

Navigation controls:

```id="0swh9k"
Next Invoice
Previous Invoice
Jump to Invoice
```

Display processing progress.

---

# Session State Tracking

Extend session state schema.

Example:

```id="nsxy2s"
st.session_state["invoice_records"]
```

Structure:

```id="l3l4ul"
{
 filename
 status
 ocr_data
 mapped_data
 validation_errors
 verified_payload
}
```

---

# Error Handling Strategy

Handle the following gracefully:

### OCR Missing Fields

Mark:

```id="3hvfmp"
status = INCOMPLETE_DATA
```

---

### Validation Failures

Display UI messages:

```id="n3rgja"
st.error()
```

Prevent approval.

---

### Unexpected Data Types

Log event and fallback to safe defaults.

---

# Logging Requirements

Use the existing logging module.

Log events:

```id="w5v7he"
OCR_NORMALIZED
ZOHO_SCHEMA_MAPPED
VALIDATION_FAILED
INVOICE_VERIFIED
INVOICE_REJECTED
```

All logs should include invoice filename.

---

# Output

After verification the system must produce:

```id="nn1kze"
verified_payload
```

Example:

```id="yph1gd"
{
 invoice_number: "...",
 customer_name: "...",
 invoice_date: "...",
 currency_code: "INR",
 line_items: [...]
}
```

This payload will be consumed in **Task 4 (Zoho API submission)**.

---

# Performance Requirements

The system must handle:

```id="akd1rg"
100+ invoices per batch
```

Verification must remain responsive.

---

# Future Compatibility

Design modules so that future integrations can easily plug in:

```id="bn7oqp"
Zoho Books API
ERP reconciliation
MIS reporting pipeline
```

---

# Expected Workflow

```id="ynx10e"
Invoice Upload
↓
Document AI OCR
↓
OCR Normalization
↓
Zoho Schema Mapping
↓
Financial Validation
↓
Human Verification
↓
Verified Payload
```

---

# Deliverables

Generate:

```id="7lh7my"
utils/zoho_mapper.py
utils/financial_validation.py
components/verification.py
integration with existing Streamlit workflow
```

Code must be **clean, modular, production-ready**, and fully commented.
