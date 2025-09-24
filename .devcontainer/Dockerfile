FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg redis-server

WORKDIR /app
COPY frontend/requirements.txt /tmp/requirements.frontend.txt
COPY backend/requirements.txt /tmp/requirements.backend.txt
RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r /tmp/requirements.frontend.txt
RUN pip install --no-cache-dir -r /tmp/requirements.backend.txt
