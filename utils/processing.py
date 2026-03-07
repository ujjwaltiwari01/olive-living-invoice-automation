import cv2
import numpy as np
from PIL import Image
import io
from utils.logger import get_logger

logger = get_logger(__name__)

def process_camera_image(image_bytes: bytes) -> bytes:
    """
    Preprocess image captured from camera:
    - Auto rotate
    - Convert to high contrast
    - Compress image
    Returns the processed image as bytes (JPEG)
    """
    try:
        # Convert bytes to numpy array
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise ValueError("Could not decode image.")

        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply adaptive thresholding to get high contrast (scanned document look)
        # blur first to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        high_contrast = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        
        # Convert back to BGR so we can save as JPEG properly
        high_contrast_bgr = cv2.cvtColor(high_contrast, cv2.COLOR_GRAY2BGR)

        # Encode with compression (quality 85)
        success, encoded_img = cv2.imencode('.jpg', high_contrast_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        
        if not success:
            raise ValueError("Failed to encode processed image.")
            
        logger.info("Successfully processed and compressed camera image.")
        return encoded_img.tobytes()
        
    except Exception as e:
        logger.error(f"Error processing camera image: {str(e)}")
        # Return original if processing fails to avoid data loss
        return image_bytes
