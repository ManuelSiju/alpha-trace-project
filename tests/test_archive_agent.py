from __future__ import annotations
import asyncio

import httpx

from core.agents.archive_agent import ArchiveAgent
from core.models.schema import Target


def _client_returning(payload, status=200):
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


def test_no_domain_returns_empty():
    assert asyncio.run(ArchiveAgent().gather(Target(name="No Domain"))) == []


def test_mailbox_email_domain_is_not_mined():
    agent = ArchiveAgent()
    assert agent._candidate_domains(Target(email="x@gmail.com")) == []


def test_custom_email_domain_is_mined():
    agent = ArchiveAgent()
    assert agent._candidate_domains(Target(email="me@example.com")) == ["example.com"]


def test_cdx_snapshots_become_a_finding(monkeypatch):
    payload = [
        ["original", "timestamp", "statuscode"],
        ["https://example.com/", "20200101000000", "200"],
        ["https://example.com/about", "20210101000000", "200"],
        ["https://example.com/about", "20210101000000", "200"],  # dup url collapses
        ["https://example.com/old-deleted-page", "20190101000000", "200"],
    ]
    monkeypatch.setattr(httpx, "AsyncClient", _client_returning(payload))

    findings = asyncio.run(ArchiveAgent().gather(Target(domain="example.com")))
    assert len(findings) == 1
    f = findings[0]
    assert f.category == "Archived Web"
    assert "old-deleted-page" in f.data["archived_urls"][-1] or \
           any("old-deleted-page" in u for u in f.data["archived_urls"])
    # dedup: /about appears once
    assert f.data["archived_urls"].count("https://example.com/about") == 1


def test_empty_cdx_returns_no_finding(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _client_returning([["original", "timestamp", "statuscode"]]))
    findings = asyncio.run(ArchiveAgent().gather(Target(domain="example.com")))
    assert findings == []


def test_cdx_network_failure_returns_no_finding(monkeypatch):
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise RuntimeError("archive.org unreachable")

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Client())
    findings = asyncio.run(ArchiveAgent().gather(Target(domain="example.com")))
    assert findings == []
