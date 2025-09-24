"""
Redis client setup and helper functions for key management and TTL handling.
"""

from redis import Redis, ConnectionError
import time
import json

from backend.logger import get_logger
from backend.config import REDIS_HOST, REDIS_PORT

logger = get_logger(__name__)

REDIS_PREFIX = "ticket:"
REDIS_RETRY_LIMIT = 3
REDIS_RETRY_DELAY = 1  # seconds

def get_redis_client():
    """
    Returns a Redis client instance with retry logic.
    Raises RuntimeError if connection fails.
    """
    for attempt in range(REDIS_RETRY_LIMIT):
        try:
            redis = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            redis.ping()
            return redis
        except ConnectionError as e:
            logger.warning(f"Redis connection failed ({attempt+1}/{REDIS_RETRY_LIMIT}): {e}")
            time.sleep(REDIS_RETRY_DELAY)
    raise RuntimeError("Unable to connect to Redis")

def make_redis_key(ticket_id: str) -> str:
    """
    Generates a consistent Redis key for a given ticket ID.
    """
    return f"{REDIS_PREFIX}{ticket_id}"

def set_redis_value(redis: Redis, key: str, mapping: dict, ttl: int = 3600):
    """
    Sets a hash value in Redis with an expiration time.
    """
    redis.setex(key, ttl, json.dumps(mapping))
    
def get_redis_value(redis: Redis, key: str):
    """
    Gets a value from Redis and parses it as JSON.
    """
    value = redis.get(key)
    if value:
        return json.loads(value)
    return None