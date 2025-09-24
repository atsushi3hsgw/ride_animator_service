"""
FastAPI entry point for the Ride Animation Service.
Handles FIT upload, animation generation, status tracking, and file retrieval.
"""
from fastapi import FastAPI, Header, HTTPException, UploadFile, File
from pydantic import BaseModel
from fastapi.responses import FileResponse
from rq import Queue

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.logger import get_logger
from backend.util import validate_fit_header
from backend.redis_client import get_redis_client
from backend.ticket import create_ticket, update_status, get_status
from backend.storage import save_fit_file, get_video_path, get_thumbnail_path
from backend.tasks import run_animation_job

logger = get_logger(__name__)
redis = get_redis_client()
queue = Queue("default", connection=redis)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB

class LimitUploadSizeMiddleware(BaseHTTPMiddleware):
    """
    Middleware to reject requests with payloads exceeding MAX_UPLOAD_SIZE.
    """
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_UPLOAD_SIZE:
            logger.warning(f"Upload rejected: size={content_length} > limit={MAX_UPLOAD_SIZE}")
            return JSONResponse(
                status_code=413,
                content={"detail": f"File too large. Maximum allowed size is {MAX_UPLOAD_SIZE // (1024 * 1024)}MB."}
            )
        return await call_next(request)

app = FastAPI(title="Ride Animation Service", description="Backend API for FIT-based ride animation generation", version="1.0")
# Add this middleware to your FastAPI app
app.add_middleware(LimitUploadSizeMiddleware)

class AnimationParams(BaseModel):
    """
    Parameters for ride animation generation.
    """
    title: str
    fps: int = 10
    dpi: int = 100
    zoom: int = 13
    step_frame: int = 60
    no_elevation_smoothing: bool = False
    tile: str = "OpenStreetMap.Mapnik"

@app.post("/upload", summary="Upload FIT file", response_description="Returns a ticket ID")
async def upload_fit(file: UploadFile = File(...)):
    """
    Accepts a FIT file upload and returns a ticket ID for tracking.
    """
        
    # Check MIME type
    if file.content_type not in ["application/octet-stream", "application/fit"]:
        logger.warning(f"Upload rejected: invalid MIME type {file.content_type}")
        raise HTTPException(status_code=400, detail="Invalid file type. Expected binary FIT file.")
        
    # Check file extension
    if not file.filename.lower().endswith(".fit"):
        logger.warning(f"Upload rejected: invalid file type {file.filename}")
        raise HTTPException(status_code=400, detail="Only .fit files are allowed")
        
    # Read file content and check size
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        logger.warning(f"Upload rejected after read: {len(content)} bytes")
        raise HTTPException(status_code=413, detail="File too large")
        
    try:    
        # Save and register ticket
        ticket_id = create_ticket()
        save_fit_file(ticket_id, content)
        update_status(ticket_id, "upload_done")
        return {"ticket_id": ticket_id}
    except Exception as e:
        logger.warning(f"Upload failed: {e}")
        update_status(ticket_id, "upload_error")
        raise HTTPException(status_code=500, detail="Failed to upload FIT file")

def on_failure_generate(job, connection, type, value, traceback):
    """
    Callback for job failure to update ticket status.
    """
    ticket_id = job.args[0]
    logger.warning(f"Failure callback triggered for ticket_id={ticket_id}, error={value}")
    update_status(ticket_id, "generate_error")
    
def on_success_generate(job, connection, result):
    """
    Callback for job success to update ticket status.
    """
    ticket_id = job.args[0]
    logger.info(f"Success callback triggered for ticket_id={ticket_id}, result={result}")
    update_status(ticket_id, "generate_done")
    
@app.post("/generate", summary="Start animation generation", response_description="Returns ticket and parameters")
def generate_animation(params: AnimationParams, ticket_id: str = Header(...)):
    """
    Starts the animation generation job for a given ticket.
    """
    info = get_status(ticket_id)
    if not info:
        raise HTTPException(status_code=404, detail="Invalid ticket ID")
    
    if info.get("status") not in ("upload_done", "generate_error", "generate_done"):
        raise HTTPException(status_code=400, detail=f"Cannot generate animation. Current status: {info.get('status')}")
    
    update_status(ticket_id, "generate_processing", params.model_dump())
    queue.enqueue(run_animation_job,
        args=(ticket_id, params.model_dump()), 
        on_failure=on_failure_generate,
        on_success=on_success_generate)
    
    return {"ticket_id": ticket_id, "params": params}

@app.get("/status", summary="Check ticket status", response_description="Returns current status and parameters")
def status(ticket_id: str = Header(...)):
    """
    Returns the current status and parameters for a given ticket.
    """
    info = get_status(ticket_id)
    if not info:
        raise HTTPException(status_code=404, detail="Invalid ticket ID")
    return info

@app.get("/video", summary="Download generated video", response_description="Returns video file")
def video(ticket_id: str = Header(...)):
    """
    Returns the generated ride animation video for a given ticket.
    """
    path = get_video_path(ticket_id)
    if not path.exists():
        logger.warning(f"Video not found: {ticket_id}")
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(path, media_type="video/mp4")

@app.get("/thumbnail", summary="Download thumbnail image", response_description="Returns thumbnail file")
def thumbnail(ticket_id: str = Header(...)):
    """
    Returns the generated thumbnail image for a given ticket.
    """
    path = get_thumbnail_path(ticket_id)
    if not path.exists():
        logger.warning(f"Thumbnail not found: {ticket_id}")
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(path, media_type="image/jpeg")