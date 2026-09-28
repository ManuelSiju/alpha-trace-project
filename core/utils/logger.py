from __future__ import annotations
import sys
from loguru import logger

from config.settings import settings


def setup_logging() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
    )
    logger.add(
        settings.LOG_FILE,
        level="DEBUG",
        rotation="50 MB",
        retention="14 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )
