"""
RQ job handler for ride animation generation.
"""
from pathlib import Path
import time
import ffmpeg

from backend.ride_route_animator import RideRouteAnimator
from backend.ticket import update_status
from backend.storage import get_video_path, get_fit_path, get_thumbnail_path
from backend.logger import get_logger
from backend.util import ensure_parent_dir

logger = get_logger(__name__)

def run_animation_job(ticket_id, params: dict):
    """
    Executes the ride animation generation job.
    Updates ticket status upon success or failure.
    """
    try:
        
        logger.info(f"Starting job: {ticket_id} with params: {params}")
        start_time = time.time()
        video_path = get_video_path(ticket_id)
        ensure_parent_dir(video_path)
        video_path.unlink(missing_ok=True)  # Remove existing video if any
        animator = RideRouteAnimator(
            input_path=get_fit_path(ticket_id),
            output_path=video_path,
            logger=logger,
            **params
        )
        animator.run()
        
        thumbnail_path = get_thumbnail_path(ticket_id)
        ensure_parent_dir(thumbnail_path)
        thumbnail_path.unlink(missing_ok=True)  # Remove existing thumbnail if any
        extract_thumbnail_from_video(video_path, thumbnail_path, width=512)

        start_time = time.time()
        logger.info(f"Job completed: {ticket_id}")
        
    except Exception as e:
        logger.error(f"Job failed: {ticket_id}  {e}")
        raise
    
    return {
        "ticket_id": ticket_id, 
        "video_path": str(video_path),
        "thumbnail_path": str(thumbnail_path),
        "elapsed": time.time() - start_time}

def extract_thumbnail_from_video(video_path: Path, thumbnail_path: Path, time: float = None, width: int = 512):
    """
    Extracts a frame from the video and saves it as a thumbnail image.
    - time: timestamp in seconds (default: middle of video)
    - width: desired width of thumbnail (height is auto-scaled)
    """
    try:
        # Get video duration
        logger.info(f"Extracting thumbnail from {video_path} to {thumbnail_path} at width={width}")
        probe = ffmpeg.probe(str(video_path))
        duration = float(probe['format']['duration'])
        timestamp = time if time is not None else duration / 2

        # Build ffmpeg command with scale filter
        logger.info(f"Video duration: {duration:.2f}s, extracting at {timestamp:.2f}s")
        (
            ffmpeg
            .input(str(video_path), ss=timestamp)
            .filter('scale', width, -1)  # -1 keeps aspect ratio
            .output(str(thumbnail_path), vframes=1)
            .run(capture_stdout=True, capture_stderr=True)
        )
        logger.info(f"Thumbnail extracted at {timestamp:.2f}s to {thumbnail_path} (width={width})")
    
    except Exception as e:
        logger.error(f"Thumbnail extraction failed: {e}")
        raise