from __future__ import annotations
import asyncio

import httpx
import pytest

from core.agents.phone_agent import PhoneAgent
from core.agents.people_search_agent import PeopleSearchAgent
from core.models.schema import Target


def test_phone_agent_no_identifier_stays_silent():
    findings = asyncio.run(PhoneAgent().gather(Target()))
    assert findings == []


def test_phone_agent_missing_library_reports_no_source(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "phonenumbers":
            raise ImportError("simulated missing dependency")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    findings = asyncio.run(PhoneAgent().gather(Target(phone="+14155552671")))
    assert len(findings) == 1
    assert findings[0].title == "No phone-intelligence source configured"
    assert findings[0].confidence == 0


def test_phone_agent_valid_number_does_not_report_no_source():
    findings = asyncio.run(PhoneAgent().gather(Target(phone="+14155552671")))
    assert findings
    assert findings[0].title != "No phone-intelligence source configured"


def test_people_search_agent_no_name_stays_silent():
    findings = asyncio.run(PeopleSearchAgent().gather(Target()))
    assert findings == []


def test_people_search_agent_no_snapshot_reports_no_source(monkeypatch):
    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"archived_snapshots": {}}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeClient())

    findings = asyncio.run(PeopleSearchAgent().gather(Target(name="Jamie Carter")))
    assert len(findings) == 1
    assert findings[0].title == "No people-search source configured"
    assert findings[0].confidence == 0


def test_people_search_agent_found_snapshot_does_not_report_no_source(monkeypatch):
    class _FakeResponse:
        status_code = 200

        def json(self):
            return {"archived_snapshots": {"closest": {"available": True, "timestamp": "20200101", "url": "http://x"}}}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeClient())

    findings = asyncio.run(PeopleSearchAgent().gather(Target(name="Jamie Carter")))
    assert findings
    assert all(f.title != "No people-search source configured" for f in findings)
