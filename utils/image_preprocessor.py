"""
Image Preprocessor (Layer 4)

Enhances invoice images before sending to Document AI to improve OCR accuracy:
  1. Correct MIME type detection
  2. Deskew (fix rotation)
  3. CLAHE contrast enhancement (for faded/low-contrast invoices)
  4. Resolution upscale (screenshots are often low DPI)

Dependencies: opencv-python, numpy  (pip install opencv-python numpy)
"""

import io
import math
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Minimum width (px) before upscaling — screenshots are often 600-900px wide
MIN_WIDTH_FOR_UPSCALE = 1200

# Max skew angle to correct (degrees) — beyond this it's likely a false detection
MAX_SKEW_ANGLE_DEG = 10.0


def _try_import_cv2():
    """Lazy import so the app still works if opencv is not installed."""
    try:
        import cv2
        import numpy as np
        return cv2, np
    except ImportError:
        logger.warning(
            "opencv-python not installed. Image preprocessing will be skipped. "
            "Run: pip install opencv-python numpy"
        )
        return None, None


def enhance_invoice_image(image_bytes: bytes, filename: str = "") -> Tuple[bytes, str]:
    """
    Applies a preprocessing pipeline to improve OCR accuracy.

    Args:
        image_bytes: Raw image bytes (PNG, JPEG, BMP, TIFF)
        filename:    Original filename (used for logging)

    Returns:
        (enhanced_bytes, mime_type) — enhanced PNG bytes and 'image/png'
        Falls back to (original_bytes, original_mime) if opencv unavailable.
    """
    cv2, np = _try_import_cv2()
    if cv2 is None:
        # Graceful fallback — return as-is
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpeg"
        mime = "image/png" if ext == "png" else "image/jpeg"
        return image_bytes, mime

    try:
        # Decode
        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            logger.warning(f"PREPROCESS: Could not decode image '{filename}', skipping.")
            return image_bytes, "image/png"

        h, w = img.shape[:2]
        logger.info(f"PREPROCESS_START: '{filename}' — original size {w}x{h}px")

        # ── Step 1: Deskew ─────────────────────────────────────────────
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Threshold to get binary image
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        # Find coordinates of non-zero pixels
        coords = np.column_stack(np.where(thresh > 0))
        if len(coords) > 100:
            angle = cv2.minAreaRect(coords)[-1]
            # minAreaRect returns angle in [-90, 0); convert to actual skew
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle

            if abs(angle) <= MAX_SKEW_ANGLE_DEG and abs(angle) > 0.3:
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                img = cv2.warpAffine(img, M, (w, h),
                                     flags=cv2.INTER_CUBIC,
                                     borderMode=cv2.BORDER_REPLICATE)
                logger.info(f"PREPROCESS_DESKEW: corrected {angle:.2f}° rotation")

        # ── Step 2: CLAHE Contrast Enhancement ─────────────────────────
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_enhanced = clahe.apply(l_channel)
        lab_enhanced = cv2.merge([l_enhanced, a_channel, b_channel])
        img = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)
        logger.info("PREPROCESS_CLAHE: contrast enhanced")

        # ── Step 3: Upscale if needed ───────────────────────────────────
        h, w = img.shape[:2]
        if w < MIN_WIDTH_FOR_UPSCALE:
            scale = MIN_WIDTH_FOR_UPSCALE / w
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            logger.info(f"PREPROCESS_UPSCALE: {w}x{h} → {new_w}x{new_h} (scale={scale:.2f}x)")

        # ── Step 4: Encode back to PNG ──────────────────────────────────
        success, buf = cv2.imencode('.png', img)
        if not success:
            logger.warning("PREPROCESS: Failed to re-encode image, returning original.")
            return image_bytes, "image/png"

        enhanced = buf.tobytes()
        logger.info(
            f"PREPROCESS_DONE: '{filename}' — "
            f"original={len(image_bytes)//1024}KB → enhanced={len(enhanced)//1024}KB"
        )
        return enhanced, "image/png"

    except Exception as e:
        logger.error(f"PREPROCESS_ERROR: '{filename}' — {e}. Using original.")
        return image_bytes, "image/png"


def should_preprocess(filename: str) -> bool:
    """Returns True for image files that benefit from preprocessing (not PDFs)."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in ("png", "jpg", "jpeg", "bmp", "tiff", "tif")
