from __future__ import annotations
import time
import aiosqlite
from pathlib import Path
from typing import Optional

from config.settings import settings
from core.memory.database import init_db


class HTTPCache:
    """Tiny TTL cache backed by sqlite. Not used by all agents — opt-in."""

    def __init__(self, db_path: Optional[Path] = None, ttl: int = None):
        self.db_path = db_path or settings.DB_PATH
        self.ttl = ttl or settings.CACHE_TTL

    async def init(self) -> None:
        await init_db(self.db_path)

    async def get(self, url: str) -> Optional[bytes]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT body, fetched_at, ttl FROM http_cache WHERE url = ?", (url,))
            row = await cur.fetchone()
            if not row:
                return None
            body, fetched, ttl = row
            if time.time() - fetched > ttl:
                return None
            return body

    async def put(self, url: str, body: bytes) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO http_cache(url, body, fetched_at, ttl) VALUES (?,?,?,?)",
                (url, body, int(time.time()), self.ttl),
            )
            await db.commit()

    async def purge_all(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("DELETE FROM http_cache")
            await db.commit()
            return cur.rowcount or 0


def purge_cache_sync(db_path: Optional[Path] = None) -> int:
    """Synchronous helper for CLI use. Returns deleted row count."""
    import sqlite3
    p = db_path or settings.DB_PATH
    if not p.exists():
        return 0
    try:
        conn = sqlite3.connect(p)
        cur = conn.execute("DELETE FROM http_cache")
        conn.commit()
        n = cur.rowcount or 0
        conn.close()
        return n
    except sqlite3.OperationalError:
        return 0
