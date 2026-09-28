from __future__ import annotations
from pathlib import Path

from core.models.schema import Target
from core.memory.session_store import SessionStore, sweep_stale_sessions, SESSION_DIR_PREFIX


def test_purge_removes_in_memory_record(tmp_path: Path):
    store = SessionStore(base_dir=tmp_path)
    sid = store.new_session(Target(email="x@example.com"))
    assert store.load(sid) is not None
    res = store.purge_session(sid, wipe_cache=False)
    assert res["session_removed"] is True
    assert store.load(sid) is None


def test_purge_deletes_encrypted_cache_dir(tmp_path: Path):
    store = SessionStore(base_dir=tmp_path)
    sid = store.new_session(Target(email="x@example.com"))
    store.cache_put("http://example.com/x", b"some cached body")
    session_dirs = list(tmp_path.glob(f"{SESSION_DIR_PREFIX}*"))
    assert len(session_dirs) == 1
    assert any(session_dirs[0].rglob("*"))

    res = store.purge_session(sid, wipe_cache=True)
    assert res["cache_files_removed"] == 1
    assert not session_dirs[0].exists()


def test_purge_all_sessions(tmp_path: Path):
    store = SessionStore(base_dir=tmp_path)
    sids = [store.new_session(Target(name=f"t{i}")) for i in range(3)]
    assert len(store.list_sessions()) == 3
    res = store.purge_all_sessions(wipe_cache=False)
    assert res["sessions_removed"] == 3
    assert store.list_sessions() == []
    for sid in sids:
        assert store.load(sid) is None


def test_no_plaintext_session_data_on_disk(tmp_path: Path):
    """The only bytes a session ever puts on disk are inside the encrypted cache file."""
    store = SessionStore(base_dir=tmp_path)
    store.new_session(Target(email="jamiecarter2004@gmail.com", name="Jamie Carter"))
    store.cache_put("http://example.com/lookup?q=jamiecarter2004", b"jamiecarter2004@gmail.com raw body")

    for p in tmp_path.rglob("*"):
        if p.is_file():
            raw = p.read_bytes()
            assert b"jamiecarter2004" not in raw
            assert b"Jamie Carter" not in raw


def test_sweep_stale_sessions_removes_crashed_dirs(tmp_path: Path):
    leftover = tmp_path / f"{SESSION_DIR_PREFIX}leftoverabc"
    leftover.mkdir()
    (leftover / "cache").mkdir()
    (leftover / "cache" / "somefile").write_bytes(b"stale")

    removed = sweep_stale_sessions(base_dir=tmp_path)

    assert removed == 1
    assert not leftover.exists()


def test_cache_get_put_roundtrip_and_expiry(tmp_path: Path):
    store = SessionStore(base_dir=tmp_path)
    store.new_session(Target(name="t"))
    store.cache_put("k1", b"hello", ttl=3600)
    assert store.cache_get("k1") == b"hello"

    store.cache_put("k2", b"stale", ttl=-1)
    assert store.cache_get("k2") is None
