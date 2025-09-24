"""
Ticket ID generation and status management using Redis.
"""

from uuid import uuid4

from backend.redis_client import get_redis_client, make_redis_key, set_redis_value, get_redis_value
from backend.logger import get_logger

logger = get_logger(__name__)
redis = get_redis_client()

def create_ticket():
    """
    Creates a new ticket ID and initializes its status.
    """
    ticket_id = str(uuid4())
    key = make_redis_key(ticket_id)
    set_redis_value(redis, key, {"status": "initial"})
    logger.info(f"Created ticket: {ticket_id}")
    return ticket_id

def update_status(ticket_id, status, params=None):
    """
    Updates the status and optional parameters for a given ticket.
    """
    key = make_redis_key(ticket_id)
    set_redis_value(redis, key, {
        "status": status,
        "params": params or {}
    })
    logger.info(f"Updated status: {ticket_id} {status}")

def get_status(ticket_id):
    """
    Retrieves the current status and parameters for a ticket.
    """
    key = make_redis_key(ticket_id)
    info = get_redis_value(redis, key)
    if not info:
        logger.warning(f"Ticket not found: {ticket_id}")
    return info
