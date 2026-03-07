import io
from typing import Tuple, Optional
from utils.logger import get_logger

logger = get_logger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

def validate_file(file_name: str, file_size: int) -> Tuple[bool, Optional[str]]:
    """
    Validates a file based on its extension and size.
    Returns (is_valid, error_message)
    """
    if file_size > MAX_FILE_SIZE_BYTES:
        err = f"File {file_name} exceeds max size of {MAX_FILE_SIZE_MB}MB."
        logger.warning(err)
        return False, err
        
    ext = file_name.split(".")[-1].lower() if "." in file_name else ""
    if ext not in ALLOWED_EXTENSIONS:
        err = f"File {file_name} has unsupported format. Allowed: {', '.join(ALLOWED_EXTENSIONS)}."
        logger.warning(err)
        return False, err
        
    return True, None
