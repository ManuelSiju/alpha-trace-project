from __future__ import annotations
import asyncio

import httpx

from core.agents.registry_agent import RegistryAgent
from core.models.schema import Target


def _client(payload, status=200):
    class _Resp:
        status_code = status

        def json(self):
            return payload

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _Resp()

    return lambda *a, **k: _Client()


def test_no_name_or_company_returns_empty():
    assert asyncio.run(RegistryAgent().gather(Target(email="x@example.com"))) == []


def test_edgar_hits_become_finding(monkeypatch):
    payload = {"hits": {"hits": [
        {"_source": {"display_names": ["CARTER JAMIE"], "file_type": "4"}},
        {"_source": {"display_names": ["EXAMPLE CORP"], "root_form": "10-K"}},
    ]}}
    monkeypatch.setattr(httpx, "AsyncClient", _client(payload))

    findings = asyncio.run(RegistryAgent().gather(Target(name="Jamie Carter")))
    assert len(findings) == 1
    assert findings[0].source == "sec-edgar"
    assert "CARTER JAMIE" in findings[0].content
    assert findings[0].data["hit_count"] == 2


def test_edgar_no_hits_returns_nothing(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _client({"hits": {"hits": []}}))
    assert asyncio.run(RegistryAgent().gather(Target(name="Nobody Here"))) == []


def test_edgar_network_failure_returns_nothing(monkeypatch):
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise RuntimeError("sec.gov unreachable")

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Client())
    assert asyncio.run(RegistryAgent().gather(Target(company="Example Corp"))) == []
