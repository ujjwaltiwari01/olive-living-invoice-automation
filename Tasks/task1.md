You are a **senior Python and Streamlit engineer with 20+ years of experience in building production-grade financial dashboards**.

Your task is to build **Task 1 of a financial automation system**: a **high-performance Streamlit dashboard for invoice ingestion** that will later connect to Google Document AI and Zoho Books.

The goal is to create a **modern, efficient, reliable UI for uploading and managing invoices**.

This dashboard must be designed for **finance teams handling large volumes of invoices**, so the system must prioritize **performance, usability, reliability, and error handling**.

---

## Technology Requirements

Use the following stack:

* Python 3.10+
* Streamlit (latest stable version)
* Pandas
* Pillow (image processing)
* OpenCV (for camera capture preprocessing)
* Python logging module
* Optional: streamlit-extras for UI enhancements

The code must follow **clean architecture and modular design**.

---

# Dashboard Objectives

The Streamlit dashboard must allow finance users to:

1. Upload single invoices
2. Upload invoices in bulk
3. Capture invoice photos using camera
4. Preview uploaded invoices
5. Track upload status
6. Prepare invoices for OCR processing
7. Handle errors gracefully

This dashboard is the **entry point of the automation pipeline**.

---

# UI/UX Requirements

The interface must be **modern and clean**.

Use:

* wide layout
* columns
* containers
* progress indicators
* status badges

The design should resemble a **professional SaaS finance tool**.

Include:

### Page Header

Title:

Olive Invoice Automation Dashboard

Subtitle:

Upload and manage invoices for automated processing

---

# Main Layout Structure

The page should contain 3 main sections:

### 1. Upload Section

Provide two upload methods:

**A) Bulk Invoice Upload**

Use Streamlit file uploader with:

* accept_multiple_files=True
* allowed file types:

  * PDF
  * PNG
  * JPG
  * JPEG

Display:

* number of files uploaded
* file names
* upload timestamp

---

**B) Camera Capture**

Allow user to capture invoice photo.

Use:

st.camera_input()

Add preprocessing:

* auto rotate
* convert to high contrast
* compress image

After capture:

* show preview
* allow user to confirm upload

---

### 2. Uploaded Invoice Preview Table

After upload, display a table containing:

Columns:

Invoice File Name
Upload Time
File Size
Upload Method (Bulk / Camera)
Status

Status values:

UPLOADED
READY_FOR_PROCESSING
ERROR

Use a pandas dataframe for tracking.

Display it using:

st.dataframe()

Add sorting and filtering capability.

---

### 3. Processing Controls

Add buttons:

Process Invoices
Clear Upload Queue

When "Process Invoices" is clicked:

* simulate processing pipeline
* change status to PROCESSING

Display progress bar.

---

# File Handling Logic

Uploaded files must be:

1. validated
2. temporarily stored
3. logged

Validation rules:

* max file size: 10MB
* allowed formats only
* reject corrupted files

If validation fails:

show user-friendly error message.

---

# Error Handling

Implement robust error handling.

Use try/except blocks for:

* file upload errors
* image decoding errors
* unsupported formats
* large file sizes

Log all errors using Python logging module.

Display clear error messages to users.

Example:

"File format not supported. Please upload PDF or image files."

---

# Performance Requirements

The dashboard must support **bulk upload of at least 100 invoices without crashing**.

Optimize by:

* processing files in batches
* avoiding unnecessary memory usage
* caching where appropriate

Use:

st.session_state

to maintain uploaded files.

---

# Responsiveness

The UI must work well on:

* laptop screens
* large monitors
* tablets

Use Streamlit layout tools:

* st.columns
* st.container
* st.expander

---

# Code Structure

The code must be clean and modular.

Structure:

main.py

Functions required:

initialize_session_state()

validate_file()

process_uploaded_files()

display_upload_section()

display_invoice_table()

handle_camera_capture()

handle_bulk_upload()

handle_processing()

Each function should be clearly documented.

---

# Additional UX Enhancements

Add:

Upload success notifications
Upload progress indicator
Expandable file previews
File count indicator

Example:

"12 invoices uploaded successfully"

---

# Future Integration Note

The system must be designed so that the uploaded files can later be passed to:

Google Document AI for OCR processing.

Do NOT implement OCR yet, but ensure the architecture supports it.

---

# Final Output

Produce a **complete working Streamlit Python script** that implements this dashboard with:

* modern UI
* efficient file handling
* strong validation
* structured code
* clear comments

Ensure the dashboard runs immediately with:

streamlit run main.py
