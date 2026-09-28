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


@pytest.fixture(autouse=True)
def _block_real_network(monkeypatch):
    """Enforces that the suite is fully offline: any test that accidentally
    exercises an unmocked network call fails loudly instead of silently
    hitting the real internet."""
    monkeypatch.setattr(socket.socket, "connect", _guard)
    monkeypatch.setattr(socket.socket, "connect_ex", _guard)
