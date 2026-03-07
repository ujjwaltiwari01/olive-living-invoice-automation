You are a **principal AI systems engineer and senior Python architect with 20+ years of experience building enterprise document automation systems**.

Your task is to implement **Task 2 of the Olive Invoice Automation System**.

This task connects the existing **Streamlit invoice ingestion dashboard (Task 1)** to **Google Document AI Invoice Parser** and returns **structured invoice data**.

You must extend the existing system without breaking the architecture.

Your solution must be **production-ready, modular, fault-tolerant, and scalable for large invoice volumes**.

---

# System Context

Task 1 has already been implemented and includes the following project structure:

```
Olive invoice automation/
│
├── main.py
├── components/
│   ├── upload.py
│   ├── preview_table.py
│   ├── controls.py
│
├── utils/
│   ├── validation.py
│   ├── processing.py
│   ├── logger.py
│
├── requirements.txt
├── test.py
```

The dashboard currently supports:

• Bulk invoice upload
• Camera capture
• File validation
• Preview table
• Processing simulation
• Session state tracking

Uploaded invoices are stored in:

```
st.session_state["uploaded_files"]
```

Each record contains metadata:

```
filename
upload_time
file_size
source
status
```

---

# Task 2 Objective

Connect the dashboard to **Google Document AI Invoice Parser** so that uploaded invoices are processed through OCR and structured invoice fields are returned.

The system must support:

• Single invoice processing
• Bulk invoice processing
• Structured response extraction
• Production error handling
• UI feedback and progress tracking

---

# Document AI Configuration (DO NOT MODIFY)

Use the following configuration exactly.

```
Project ID: olive-invoice-automation
Location: us
Processor ID: b6c8916bc52a549
```

Authentication JSON key path:

```
D:\Olive invoice automation\olive-invoice-automation-a4c87dd56907.json
```

Use this key with:

```
google.oauth2.service_account
```

---

# Libraries Required

Ensure the following packages are installed:

```
google-cloud-documentai
google-auth
pandas
streamlit
opencv-python
Pillow
```

---

# New Module to Create

Create a new utility module:

```
utils/document_ai.py
```

This module will handle all OCR operations.

---

# Required Functions

Implement the following functions inside `document_ai.py`.

---

## 1. Initialize Document AI Client

```
get_document_ai_client()
```

Responsibilities:

• Load service account credentials
• Create DocumentProcessorServiceClient
• Return the client instance

---

## 2. Process Single Invoice

```
process_invoice(file_bytes)
```

Responsibilities:

• Send the document to Document AI
• Handle both PDF and image files
• Parse the response

Return structured data:

```
{
  "supplier_name": "",
  "invoice_id": "",
  "invoice_date": "",
  "total_amount": "",
  "tax_amount": "",
  "line_items": []
}
```

---

## 3. Extract Structured Entities

```
extract_entities(document)
```

Responsibilities:

Parse Document AI entities such as:

```
supplier_name
invoice_id
invoice_date
total_amount
tax_amount
line_item
```

Return normalized Python dictionary.

---

## 4. Batch Processing

```
process_batch_invoices(files)
```

Responsibilities:

• Accept list of uploaded invoice files
• Process invoices sequentially
• Return structured data list

Output format:

```
[
  {
    "filename": "...",
    "status": "processed",
    "data": {...}
  }
]
```

---

# Error Handling Requirements

The system must gracefully handle:

### Invalid file format

Return:

```
status: validation_error
```

---

### OCR failure

Return:

```
status: ocr_failed
```

---

### API timeout

Retry up to:

```
3 attempts
```

Use exponential backoff.

---

### Authentication failure

Display Streamlit error message:

```
Document AI authentication failed.
```

---

# Integration with Streamlit

Modify `components/controls.py`.

Replace the **processing simulation** with actual OCR.

Workflow:

```
User clicks "Process Invoices"
        ↓
Retrieve uploaded files
        ↓
Call process_batch_invoices()
        ↓
Update session state
        ↓
Display results
```

---

# UI Feedback

Display real-time progress:

```
st.progress()
```

For each invoice:

```
Processing invoice 3 of 10
```

Update status in session state:

```
UPLOADED
PROCESSING
OCR_COMPLETE
ERROR
```

---

# Results Display

After processing, show extracted fields.

Add a new section in the dashboard:

```
Extracted Invoice Data
```

Display table:

```
Supplier
Invoice Number
Date
Total Amount
Tax Amount
```

Use:

```
st.dataframe()
```

---

# Performance Requirements

The system must support processing:

```
100+ invoices per batch
```

Optimizations required:

• reuse Document AI client
• avoid reloading credentials repeatedly
• minimize memory usage

---

# Logging Requirements

Use existing:

```
utils/logger.py
```

Log events:

```
OCR_START
OCR_SUCCESS
OCR_FAILURE
API_ERROR
```

---

# Production Considerations

Design code so future integrations can be added easily.

The next stages of development will include:

```
Zoho Books API integration
MIS reporting pipeline
```

So keep the architecture flexible.

---

# Expected Final Workflow

```
Streamlit Dashboard
        ↓
Invoice Upload
        ↓
Validation
        ↓
Document AI OCR
        ↓
Structured Data Extraction
        ↓
Display Results
```

---

# Deliverables

Generate:

1. `utils/document_ai.py`
2. Updated `components/controls.py`
3. Example usage inside `main.py`

All code must be **clean, modular, and production ready**.

Include detailed comments explaining logic.

The system must run without requiring any manual configuration since the processor ID, project ID, and credential path are already defined.
