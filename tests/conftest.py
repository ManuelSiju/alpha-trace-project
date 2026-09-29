import asyncio
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class NetworkDisabledError(RuntimeError):
    pass


def _guard(*args, **kwargs):
    raise NetworkDisabledError(
        "Real network access is disabled in tests. Mock the HTTP client, "
        "subprocess, or library call instead of hitting a real socket."
    )


async def _guard_subprocess(*args, **kwargs):
    raise NetworkDisabledError(
        "Real subprocess execution (e.g. sherlock, holehe) is disabled in "
        "tests. Mock asyncio.create_subprocess_exec or the agent's own "
        "binary-lookup method instead."
    )


@pytest.fixture(autouse=True)
def _block_real_network(monkeypatch):
    """Enforces that the suite is fully offline: any test that accidentally
    exercises an unmocked network call fails loudly instead of silently
    hitting the real internet. This covers subprocess-spawned tools too
    (sherlock, holehe) -- socket-blocking alone doesn't touch a child
    process's own network stack, which is how a stale-venv fix elsewhere in
    this project silently turned previously-instant offline tests into
    multi-minute real sherlock sweeps until this was added."""
    monkeypatch.setattr(socket.socket, "connect", _guard)
    monkeypatch.setattr(socket.socket, "connect_ex", _guard)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _guard_subprocess)
