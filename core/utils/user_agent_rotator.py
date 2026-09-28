from __future__ import annotations
import random
from config.settings import settings


def random_user_agent() -> str:
    return random.choice(settings.USER_AGENTS)


def default_headers() -> dict:
    return {
        "User-Agent": random_user_agent(),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/json,application/xhtml+xml;q=0.9,*/*;q=0.8",
    }
