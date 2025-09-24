"""
Logger configuration for the Ride Animation Service.
Provides a shared logger instance across all backend modules.
"""

import logging

def get_logger(name="ride_service") -> logging.Logger:
    """
    Returns a configured logger instance.
    Ensures consistent formatting and avoids duplicate handlers.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger