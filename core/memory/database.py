from __future__ import annotations
import aiosqlite
from pathlib import Path

from config.settings import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  target_json TEXT NOT NULL,
  briefing_json TEXT,
  chat_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS http_cache (
  url TEXT PRIMARY KEY,
  body BLOB,
  fetched_at INTEGER NOT NULL,
  ttl INTEGER NOT NULL
);
"""


async def init_db(path: Path | None = None) -> None:
    p = path or settings.DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(p) as db:
        await db.executescript(SCHEMA)
        await db.commit()
