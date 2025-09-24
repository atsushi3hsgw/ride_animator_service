"""
Handles file storage for FIT files, video output, and thumbnails.
"""

from pathlib import Path
from backend.logger import get_logger
from backend.config import VIDEO_FILES_DIR, FIT_FILES_DIR, THUMBNAIL_FILES_DIR
from backend.util import ensure_parent_dir

logger = get_logger(__name__)

def get_fit_path(ticket_id):
    """
    Returns the expected path for the FIT file.
    """
    return Path(f"{FIT_FILES_DIR}/{ticket_id}.fit")

def save_fit_file(ticket_id, content: bytes):
    """
    Saves the uploaded FIT file to disk.
    """
    path = Path(get_fit_path(ticket_id))
    ensure_parent_dir(path)
    path.write_bytes(content)
    logger.info(f"Saved FIT file: {path}")

def get_video_path(ticket_id):
    """
    Returns the expected path for the generated video file.
    """
    return Path(f"{VIDEO_FILES_DIR}/{ticket_id}.mp4")

def get_thumbnail_path(ticket_id):
    """
    Returns the expected path for the generated thumbnail image.
    """
    return Path(f"{THUMBNAIL_FILES_DIR}/{ticket_id}.jpg")