import os
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

VIDEO_FILES_DIR      = os.environ.get("VIDEO_FILES_DIR", "/app/storage/videos")
FIT_FILES_DIR        = os.environ.get("FIT_FILES_DIR", "/app/storage/fits")
THUMBNAIL_FILES_DIR  = os.environ.get("THUMBNAIL_FILES_DIR", "/app/storage/thumbnails")