from __future__ import annotations
import platform

import pytest

from core.llm.ollama_client import OllamaUnavailable
from core.llm import preflight


class _FakeLLM:
    def __init__(self, healthy: bool, ensure_raises: bool = False):
        self.healthy = healthy
        self.ensure_raises = ensure_raises
        self.model = "qwen2.5:3b-instruct"

    def health_check(self) -> bool:
        return self.healthy

    def ensure_model(self) -> None:
        if self.ensure_raises:
            raise RuntimeError("connection refused while pulling")


def test_package_missing(monkeypatch):
    def raise_unavailable():
        raise OllamaUnavailable("ollama package not installed")

    monkeypatch.setattr(preflight, "get_llm", raise_unavailable)
    res = preflight.check_ollama()
    assert res.status == "package_missing"
    assert res.fix == "pip install ollama"
    assert "Traceback" not in res.message


def test_server_down(monkeypatch):
    monkeypatch.setattr(preflight, "get_llm", lambda: _FakeLLM(healthy=False))
    res = preflight.check_ollama()
    assert res.status == "server_down"
    assert res.fix is not None
    if platform.system() == "Windows":
        assert "ollama serve" in res.fix.lower()
    else:
        assert res.fix == "ollama serve &"


def test_model_pull_failed_hides_raw_exception(monkeypatch):
    monkeypatch.setattr(preflight, "get_llm", lambda: _FakeLLM(healthy=True, ensure_raises=True))
    res = preflight.check_ollama()
    assert res.status == "model_pull_failed"
    assert "connection refused" not in res.message
    assert res.fix == "ollama pull qwen2.5:3b-instruct"


def test_ok(monkeypatch):
    monkeypatch.setattr(preflight, "get_llm", lambda: _FakeLLM(healthy=True))
    res = preflight.check_ollama()
    assert res.status == "ok"
    assert res.fix is None
    assert "qwen2.5:3b-instruct" in res.message
