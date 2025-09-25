import os
import time
import logging
import requests
import streamlit as st
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
API_BASE_HOST = os.environ.get("API_BASE_HOST", "http://localhost")
API_BASE_PORT = os.environ.get("API_BASE_PORT", "8000")
API_BASE = f"{API_BASE_HOST}:{API_BASE_PORT}"

def setup_logger(name=__name__):
    logger = logging.getLogger(name)
    if not logger.hasHandlers():
        level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_str, logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s in %(name)s: %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
    return logger

logger = setup_logger("RideAnimationGenerator")

# Initialize session state
if "status" not in st.session_state:
    st.session_state.status = None
    st.session_state.ticket_id = ""
    st.session_state.error_message = ""
    st.session_state.thumbnail = None
    st.session_state.video = None

# Fetch status if ticket_id is set
if st.session_state.ticket_id:
    try:
        logger.debug(f"Fetching status for ticket_id={st.session_state.ticket_id}")
        res = requests.get(f"{API_BASE}/status", headers={"ticket-id": st.session_state.ticket_id})
        if res.status_code == 200:
            info = res.json()
            st.session_state.error_message = ""
            new_status = info.get("status")
            if st.session_state.status != new_status:
                logger.info(f"{st.session_state.ticket_id} Status changed:{st.session_state.status} to {new_status}")
            st.session_state.status = new_status
        else:
            logger.warning(f"Status fetch error: {res.status_code}, {res.text}")
            st.session_state.error_message = res.json().get("detail", "Unknown error")
    except Exception as e:
        logger.error(f"Failed to fetch status: {e}")
        st.session_state.error_message = f"Failed to fetch status: {e}"
        st.session_state.status = None

    # Auto-refresh if processing
    if st.session_state.status == "generate_processing":
        with st.spinner("Generating animation... Please wait."):
            time.sleep(5)
            st.rerun()

# UI
st.title("🚴 Ride Animation Generator")

# -------------------------------
# 📋 Status Section
# -------------------------------
st.header("Status")
if st.button("🔄 Reload Status"):
    st.rerun()

status = st.session_state.status
ticket_id = st.session_state.ticket_id
error_message = st.session_state.error_message

st.text(f"Status: {status}")
st.text(f"Ticket ID: {ticket_id}")
if error_message:
    st.error(error_message)

if status == "upload_done":
    st.success("Upload completed.")
elif status == "upload_error":
    st.error("Upload failed.")
elif status == "generate_error":
    st.error("Animation generation failed.")
elif status == "generate_done":
    st.success("Animation generation completed.")
elif status is None:
    st.info("Waiting for upload.")
else:
    st.warning(f"Unknown status: {status}")

# -------------------------------
# Upload Section
# -------------------------------
st.header("Upload FIT File")

st.markdown("**Note:** Maximum file size is **20MB**. Only `.fit` files are accepted.")
uploaded_file = st.file_uploader("Select a FIT file", type=["fit"])
if st.button("📤 Upload") and uploaded_file:
    try:
        logger.info(f"Uploading file: {uploaded_file.name}, size: {uploaded_file.size} bytes")
        files = {
            "file": ("filename.fit", uploaded_file.getvalue(), "application/octet-stream")
        }
        res = requests.post(f"{API_BASE}/upload", files=files)
        # res = requests.post(f"{API_BASE}/upload", files={"file": uploaded_file})
        if res.status_code == 200:
            data = res.json()
            logger.info(f"Upload successful, ticket_id={st.session_state.ticket_id}")
            st.session_state.ticket_id = data["ticket_id"]
            st.session_state.thumbnail = None
            st.session_state.video = None
            st.session_state.error_message = ""
            st.rerun()
        else:
            st.session_state.error_message = res.json().get("detail", "Upload failed")
    except Exception as e:
        logger.errror(f"Upload request failed: {e}")
        st.session_state.error_message = f"Upload request failed: {e}"

# -------------------------------
# Animation Generation Section
# -------------------------------
if status in ["upload_done", "generate_error", "generate_done"]:
    st.header("Generate Animation")

    col1, col2, col3 = st.columns(3)
    with col1:
        title = st.text_input("Title", value="My Ride")
        zoom = st.selectbox("Zoom", [12, 13, 14], index=1)
    with col2:
        fps = st.selectbox("FPS", [10, 30, 60], index=1)
        step_frame = st.selectbox("Step Frame", [30, 60, 120], index=1)
    with col3:
        dpi = st.selectbox("DPI", [50, 100, 150], index=1)
        no_smoothing = st.checkbox("Disable Elevation Smoothing", value=False)

    tile = st.selectbox("Map Tile", [
        "OpenStreetMap.Mapnik",
        "OpenStreetMap.HOT.mp4",
        "Esri.WorldImagery",
        "Esri.WorldStreetMap",
        "CartoDB.DarkMatter",
        "CartoDB.Voyager"
    ], index=0)

    if st.button("🎬 Generate"):
        try:
            logger.info(f"Requesting generation for ticket_id={ticket_id} with title={title}, fps={fps}, dpi={dpi}, zoom={zoom}, step_frame={step_frame}, no_smoothing={no_smoothing}, tile={tile}")
            res = requests.post(f"{API_BASE}/generate",
                headers={"ticket-id": ticket_id},
                json={
                    "title": title,
                    "fps": fps,
                    "dpi": dpi,
                    "zoom": zoom,
                    "step_frame": step_frame,
                    "no_elevation_smoothing": no_smoothing,
                    "tile": tile
                }
            )
            if res.status_code != 200:
                logger.warning(f"Generation request failed: {res.status_code}, {res.text}")
                st.session_state.error_message = res.json().get("detail", "Generation failed")
            else:
                logger.info("Generation request accepted")
                st.session_state.error_message = ""
                st.session_state.thumbnail = None
                st.session_state.video = None
                st.rerun()
        except Exception as e:
            logger.error(f"Generation request failed: {e}")
            st.session_state.error_message = f"Generation request failed: {e}"

# -------------------------------
# Result Section
# -------------------------------
if status == "generate_done":
    st.header("Animation Result")

    # Fetch thumbnail once
    if st.session_state.thumbnail is None:
        try:
            logger.info(f"Fetching thumbnail for ticket_id={ticket_id}")
            thumb_res = requests.get(f"{API_BASE}/thumbnail", headers={"ticket-id": ticket_id})
            if thumb_res.status_code == 200:
                st.session_state.thumbnail = thumb_res.content
                logger.info("Thumbnail fetched successfully")
            else:
                logger.warning(f"Thumbnail fetch failed: {thumb_res.status_code}, {thumb_res.text}")
                st.session_state.error_message = thumb_res.json().get("detail", "Thumbnail fetch failed")
        except Exception as e:
            logger.exception("Thumbnail fetch error")
            st.session_state.error_message = f"Thumbnail fetch error: {e}"
            
    # Display thumbnail if available
    if st.session_state.thumbnail:
        st.image(st.session_state.thumbnail, caption="Thumbnail")

    # Fetch video once
    if st.session_state.video is None:
        try:
            logger.info(f"Fetching video for ticket_id={ticket_id}")
            video_res = requests.get(f"{API_BASE}/video", headers={"ticket-id": ticket_id})
            if video_res.status_code == 200:
                st.session_state.video = video_res.content
                logger.info("Video fetched successfully")
            else:
                logger.warning(f"Video fetch failed: {video_res.status_code}, {video_res.text}")
                st.session_state.error_message = video_res.json().get("detail", "Video fetch failed")
                
        except Exception as e:
            logger.exception("Video fetch error")
            st.session_state.error_message = f"Video fetch error: {e}"
            
    if st.session_state.video:
        st.download_button("📥 Download Video", st.session_state.video, file_name="ride.mp4")
