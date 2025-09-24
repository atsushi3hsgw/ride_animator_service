"""
utility functions used by both frontend and backend.
"""
from pathlib import Path
from backend.logger import get_logger

logger = get_logger(__name__)

def validate_fit_header(content: bytes) -> bool:
    """
    Validates the FIT file header structure.
    Returns True if valid, False otherwise.
    
    0 Header size (typically 14)
    1–7 Protocol version, profile version, data size, etc.
    8–11 Data size (4 bytes)
    12–13 Identifier “.FIT” (ASCII: 0x2E 0x46 0x49 0x54)
    14 CRC (optional)
    """
    try:
        if len(content) < 14:
            return False
        if content[0] != 14:
            return False
        if content[8:12] != b'.FIT':
            return False
        return True
    except Exception:
        return False

def ensure_parent_dir(filepath: Path) -> None:
    """
    Ensures that the parent directory of the given filepath exists.
    Creates the directory if it does not exist.
    """
    parent = filepath.parent
    logger.info(f"Ensuring directory {parent}")
    if parent == Path(".") or str(parent) == "":
        return
    parent.mkdir(parents=True, exist_ok=True)