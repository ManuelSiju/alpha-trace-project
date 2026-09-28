from __future__ import annotations
import atexit
import base64
import gc
import hashlib
import json
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from core.models.schema import SessionRecord, Target, Briefing

SESSION_DIR_PREFIX = ".alpha-tracer-session-"


def sweep_stale_sessions(base_dir: Optional[Path] = None) -> int:
    """Delete leftover per-session temp directories from crashed prior runs.

    Call once at app launch, before any new session is created, so a crash that
    skipped normal purge never leaves case data sitting on disk indefinitely.
    """
    base = base_dir or Path(tempfile.gettempdir())
    removed = 0
    for p in base.glob(f"{SESSION_DIR_PREFIX}*"):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            removed += 1
    return removed


class SessionStore:
    """RAM-first case store for a single active session.

    The session record (target, briefing, chat history) lives only in process
    memory. If disk is needed at all — currently only for the opt-in HTTP
    response cache — it goes through a per-session temp directory encrypted
    with a random key held only in memory (crypto-shred: dropping the key
    renders anything left on disk unreadable, and the directory is deleted on
    purge regardless).

    This does not guarantee data is unrecoverable from disk at the hardware
    level (SSD wear-leveling, swap, copy-on-write filesystems, and OS page
    cache can all retain fragments Python cannot reach) — see README's
    privacy-limits section.
    """

    def __init__(self, base_dir: Optional[Path] = None):
        self._base_dir = base_dir or Path(tempfile.gettempdir())
        self._records: dict[str, SessionRecord] = {}
        self._key: Optional[bytes] = None
        self._fernet: Optional[Fernet] = None
        self._session_dir: Optional[Path] = None
        self._active_session_id: Optional[str] = None
        atexit.register(self._atexit_purge)

    # -- lifecycle -----------------------------------------------------

    def new_session(self, target: Target) -> str:
        sid = f"ses_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self._records[sid] = SessionRecord(session_id=sid, target=target)
        self._active_session_id = sid
        self._key = Fernet.generate_key()
        self._fernet = Fernet(self._key)
        self._session_dir = Path(tempfile.mkdtemp(prefix=SESSION_DIR_PREFIX, dir=self._base_dir))
        return sid

    def purge_session(self, session_id: str, wipe_cache: bool = True) -> dict:
        """Drop the in-memory record, drop the key, delete the temp dir, gc.collect()."""
        out = {"session_removed": False, "cache_files_removed": 0}
        if session_id in self._records:
            del self._records[session_id]
            out["session_removed"] = True
        if wipe_cache:
            out["cache_files_removed"] = self._destroy_disk_state()
        else:
            self._key = None
            self._fernet = None
        if self._active_session_id == session_id:
            self._active_session_id = None
        gc.collect()
        return out

    def purge_all_sessions(self, wipe_cache: bool = True) -> dict:
        removed = len(self._records)
        self._records.clear()
        cache_files = self._destroy_disk_state() if wipe_cache else 0
        self._active_session_id = None
        gc.collect()
        return {"sessions_removed": removed, "cache_files_removed": cache_files}

    def _destroy_disk_state(self) -> int:
        n = 0
        if self._session_dir and self._session_dir.exists():
            n = sum(1 for _ in self._session_dir.rglob("*") if _.is_file())
            shutil.rmtree(self._session_dir, ignore_errors=True)
        self._key = None
        self._fernet = None
        self._session_dir = None
        return n

    def _atexit_purge(self) -> None:
        # Crash-free process exit without an explicit purge: still wipe disk state.
        if self._session_dir and self._session_dir.exists():
            shutil.rmtree(self._session_dir, ignore_errors=True)

    # -- record access (in-memory only) ---------------------------------

    def load(self, session_id: str) -> Optional[SessionRecord]:
        return self._records.get(session_id)

    def save_briefing(self, session_id: str, briefing: Briefing) -> None:
        rec = self._records.get(session_id)
        if not rec:
            return
        rec.briefing = briefing
        rec.updated_at = datetime.now(timezone.utc)

    def append_chat(self, session_id: str, question: str, answer: str) -> None:
        rec = self._records.get(session_id)
        if not rec:
            return
        rec.chat_history.append({
            "question": question,
            "answer": answer,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        rec.updated_at = datetime.now(timezone.utc)

    def list_sessions(self) -> list[str]:
        """Sessions active in this process's memory right now (nothing persists across runs)."""
        return list(self._records.keys())

    # -- opt-in encrypted disk cache (e.g. for agent HTTP responses) ----

    def cache_get(self, key: str) -> Optional[bytes]:
        if not self._session_dir or not self._fernet:
            return None
        p = self._cache_path(key)
        if not p.exists():
            return None
        try:
            payload = json.loads(self._fernet.decrypt(p.read_bytes()))
        except (InvalidToken, ValueError, OSError):
            return None
        if time.time() - payload["ts"] > payload["ttl"]:
            p.unlink(missing_ok=True)
            return None
        return base64.b64decode(payload["body"])

    def cache_put(self, key: str, body: bytes, ttl: int = 3600) -> None:
        if not self._session_dir or not self._fernet:
            return
        p = self._cache_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({
            "ts": time.time(),
            "ttl": ttl,
            "body": base64.b64encode(body).decode("ascii"),
        }).encode("utf-8")
        p.write_bytes(self._fernet.encrypt(payload))

    def _cache_path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._session_dir / "cache" / h
