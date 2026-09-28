from __future__ import annotations
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.models.schema import SessionRecord, Target, Briefing
from config.settings import settings


class SessionManager:
    """File-based session store. One JSON per session under data/sessions/."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or settings.SESSION_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self.root / f"{session_id}.json"

    def new_session(self, target: Target) -> str:
        sid = f"ses_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        rec = SessionRecord(session_id=sid, target=target)
        self._write(rec)
        return sid

    def save_briefing(self, session_id: str, briefing: Briefing) -> None:
        rec = self.load(session_id)
        if not rec:
            return
        rec.briefing = briefing
        rec.updated_at = datetime.utcnow()
        self._write(rec)

    def append_chat(self, session_id: str, question: str, answer: str) -> None:
        rec = self.load(session_id)
        if not rec:
            return
        rec.chat_history.append({"question": question, "answer": answer, "ts": datetime.utcnow().isoformat()})
        rec.updated_at = datetime.utcnow()
        self._write(rec)

    def load(self, session_id: str) -> Optional[SessionRecord]:
        p = self._path(session_id)
        if not p.exists():
            return None
        try:
            return SessionRecord.model_validate_json(p.read_text("utf-8"))
        except Exception:
            return None

    def list_sessions(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("ses_*.json"))

    def _write(self, rec: SessionRecord) -> None:
        self._path(rec.session_id).write_text(rec.model_dump_json(indent=2), encoding="utf-8")

    def purge_session(self, session_id: str, wipe_cache: bool = True) -> dict:
        """Delete session JSON and optionally wipe HTTP cache.

        Returns dict with counts so the caller can confirm to user.
        """
        from core.memory.cache_manager import purge_cache_sync
        out = {"session_removed": False, "cache_rows_removed": 0}
        p = self._path(session_id)
        if p.exists():
            try:
                p.unlink()
                out["session_removed"] = True
            except OSError:
                pass
        if wipe_cache:
            out["cache_rows_removed"] = purge_cache_sync()
        return out

    def purge_all_sessions(self, wipe_cache: bool = True) -> dict:
        from core.memory.cache_manager import purge_cache_sync
        removed = 0
        for p in self.root.glob("ses_*.json"):
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
        cache_rows = purge_cache_sync() if wipe_cache else 0
        return {"sessions_removed": removed, "cache_rows_removed": cache_rows}
