#!/bin/bash
set -e
cd /app

echo "Starting with:"
echo "REDIS_HOST=$REDIS_HOST"
echo "REDIS_PORT=$REDIS_PORT"
echo "REDIS_DB=$REDIS_DB"
echo "API_BASE_HOST=$API_BASE_HOST"
echo "API_BASE_PORT=$API_BASE_PORT"

# Start services
service redis-server restart
mkdir -p /var/log

nohup rq worker --url redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB} >> /var/log/worker.log 2>&1 &
nohup uvicorn backend.main:app --host 0.0.0.0 --port ${API_BASE_PORT} --reload >> /var/log/backend.log 2>&1 & 
nohup streamlit run frontend/main.py --server.port=8501 --server.address=0.0.0.0 >> /var/log/frontend.log 2>&1 &