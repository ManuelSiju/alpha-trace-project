from __future__ import annotations
from pathlib import Path

import pytest

from core.models.schema import Target, Briefing
from core.memory.session_manager import SessionManager


def test_purge_removes_session_json(tmp_path: Path):
    sm = SessionManager(root=tmp_path)
    sid = sm.new_session(Target(email="x@example.com"))
    assert (tmp_path / f"{sid}.json").exists()
    res = sm.purge_session(sid, wipe_cache=False)
    assert res["session_removed"] is True
    assert not (tmp_path / f"{sid}.json").exists()


def test_purge_all_sessions(tmp_path: Path):
    sm = SessionManager(root=tmp_path)
    for i in range(3):
        sm.new_session(Target(name=f"t{i}"))
    assert len(list(tmp_path.glob("ses_*.json"))) == 3
    res = sm.purge_all_sessions(wipe_cache=False)
    assert res["sessions_removed"] == 3
    assert len(list(tmp_path.glob("ses_*.json"))) == 0
