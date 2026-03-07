import streamlit as st
import datetime
import uuid
from typing import List, Any
from utils.logger import get_logger
from utils.validation import validate_file, ALLOWED_EXTENSIONS
from utils.processing import process_camera_image

logger = get_logger(__name__)

def process_uploaded_files(files: List[Any], method: str):
    """
    Process both bulk upload and camera capture files.
    Validates, logs, and stores them in session state.
    """
    success_count = 0
    for file in files:
        if file is None:
            continue
            
        file_name = file.name
        file_size = file.size
        
        # Validation
        is_valid, err_msg = validate_file(file_name, file_size)
        if not is_valid:
            st.error(err_msg)
            continue
            
        # Optional: Save bytes internally or just track metadata
        # For memory efficiency with 100+ files, we only store metadata in the state DataFrame block
        # In a real app we might write to a temp directory to save RAM
        
        new_invoice = {
            "id": str(uuid.uuid4()),
            "Invoice File Name": file_name,
            "Upload Time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "File Size (KB)": round(file_size / 1024, 2),
            "Upload Method": method,
            "Status": "UPLOADED",
            "bytes": file.getvalue()
        }
        
        st.session_state.uploaded_invoices.append(new_invoice)
        success_count += 1
        
    if success_count > 0:
        st.success(f"{success_count} invoice(s) uploaded successfully via {method}.")
        logger.info(f"Successfully processed {success_count} files via {method}")


def handle_bulk_upload(uploaded_files: List[Any]):
    """Handles logic for bulk file uploader."""
    if uploaded_files:
        process_uploaded_files(uploaded_files, "Bulk")


def handle_camera_capture(camera_image: Any):
    """Handles logic for camera capture."""
    if camera_image:
        try:
            # Process the image to high contrast/compress
            processed_bytes = process_camera_image(camera_image.getvalue())
            
            # Since camera_input creates a file object, we simulate one with processed bytes if needed
            # But here we just mock the file object for `process_uploaded_files` to keep it uniform
            class MockFile:
                def __init__(self, name, data):
                    self.name = name
                    self.size = len(data)
                    self._data = data
                def getvalue(self):
                    return self._data
            
            # Rename the file nicely
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            mock_file = MockFile(f"capture_{timestamp}.jpg", processed_bytes)
            
            process_uploaded_files([mock_file], "Camera")
        except Exception as e:
            msg = f"Failed to process camera image: {str(e)}"
            st.error(msg)
            logger.error(msg)


def display_upload_section():
    """Renders the upload area (Drag & drop + Camera)."""
    st.markdown("### Upload Invoices")
    
    tab1, tab2 = st.tabs(["📁 Bulk Upload", "📸 Camera Capture"])
    
    with tab1:
        st.markdown("**Upload multiple invoices at once (Max 10MB per file)**")
        uploaded_files = st.file_uploader(
            "Drag and drop PDF, PNG, JPG files here", 
            accept_multiple_files=True,
            type=list(ALLOWED_EXTENSIONS),
            key="bulk_uploader"
        )
        if st.button("Upload Selected Files", key="btn_bulk_upload"):
            if uploaded_files:
                with st.spinner("Processing files..."):
                    handle_bulk_upload(uploaded_files)
            else:
                st.warning("Please select files to upload first.")
                
    with tab2:
        st.markdown("**Capture a document directly from your camera**")
        
        # Camera configuration for mobile flexibility
        # In current versions of Streamlit, the browser natively prompts the mobile user to 
        # switch the camera via the built-in browser UI when multiple cameras exist.
        
        camera_image = st.camera_input("Take a picture", key="camera_input_default")
        
        if camera_image:
            # Preview is automatically shown by st.camera_input
            if st.button("Confirm and Upload Capture", key="btn_camera_upload_default"):
                with st.spinner("Optimizing image..."):
                    handle_camera_capture(camera_image)
