from __future__ import annotations
import asyncio

import httpx

from core.models.schema import Target
from core.agents.email_agent import EmailAgent


TEST_EMAIL = "jamiecarter2004@gmail.com"


def test_email_agent_metadata_finding():
    findings = asyncio.run(EmailAgent().gather(Target(email=TEST_EMAIL)))
    # At least the metadata Finding must exist (network-independent).
    titles = [f.title for f in findings]
    assert any("Email metadata" in (t or "") for t in titles)
    meta = next(f for f in findings if f.title == "Email metadata")
    assert meta.data["domain"] == "gmail.com"
    assert meta.data["provider"] == "Google"
    assert meta.data["disposable"] is False
    assert meta.data["pattern"] == "name+year"


def test_gravatar_profile_json_is_parsed(monkeypatch):
    """When a Gravatar avatar exists, the public profile JSON (name, location,
    linked accounts -- the person's own self-published data) is pulled and
    surfaced, not just 'avatar exists'."""
    profile_json = {
        "entry": [{
            "displayName": "Jamie C",
            "name": {"givenName": "Jamie", "familyName": "Carter"},
            "currentLocation": "Metropolis",
            "aboutMe": "Software engineer and coffee enthusiast.",
            "accounts": [
                {"url": "https://github.com/jcarter"},
                {"url": "https://twitter.com/jcarter"},
            ],
        }]
    }

    class _Resp:
        def __init__(self, status, payload=None):
            self.status_code = status
            self._payload = payload

        def json(self):
            return self._payload

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def head(self, url):
            return _Resp(200)

        async def get(self, url):
            return _Resp(200, profile_json)

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Client())

    finding = asyncio.run(EmailAgent()._gravatar("jamie@example.com"))
    assert finding is not None
    assert finding.data["full_name"] == "Jamie Carter"
    assert finding.data["location"] == "Metropolis"
    assert "https://github.com/jcarter" in finding.data["linked_accounts"]
    assert len(finding.data["linked_accounts"]) == 2


def test_gravatar_absent_returns_none(monkeypatch):
    class _Resp:
        status_code = 404

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def head(self, url):
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Client())
    assert asyncio.run(EmailAgent()._gravatar("nobody@example.com")) is None
