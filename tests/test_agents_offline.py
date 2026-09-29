from __future__ import annotations
import asyncio
import shutil
import sys

import httpx
import pytest

from core.agents.username_agent import UsernameAgent
from core.agents.domain_agent import DomainAgent
from core.agents.breach_agent import BreachAgent
from core.agents.image_agent import ImageAgent
from core.agents.social_media_agent import SocialMediaAgent
from core.agents.github_agent import GitHubAgent
from core.models.schema import Target


class _FakeClient:
    def __init__(self, get_impl):
        self._get_impl = get_impl

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        return await self._get_impl(*a, **k)


def _raising_get(*a, **k):
    async def _inner(*a2, **k2):
        raise RuntimeError("network down")
    return _inner()


# ---------------------------------------------------------------- UsernameAgent

def test_username_agent_no_candidates_returns_empty():
    assert asyncio.run(UsernameAgent().gather(Target())) == []


def test_username_agent_sherlock_not_installed_returns_empty(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(sys, "executable", "/nonexistent/interpreter")
    findings = asyncio.run(UsernameAgent().gather(Target(username="somebody")))
    assert findings == []


def test_username_agent_missing_binary_returns_empty(monkeypatch):
    async def fake_exec(*a, **k):
        raise FileNotFoundError("no such file")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = asyncio.run(UsernameAgent()._run_one("/bin/fake-sherlock", "somebody"))
    assert result == []


def test_username_agent_subprocess_timeout_returns_empty(monkeypatch):
    class FakeProc:
        def kill(self):
            pass

        async def communicate(self):
            return (b"", b"")

    async def fake_exec(*a, **k):
        return FakeProc()

    async def fake_wait_for(coro, timeout):
        coro.close()
        raise asyncio.TimeoutError()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    result = asyncio.run(UsernameAgent()._run_one("/bin/fake-sherlock", "somebody"))
    assert result == []


# ------------------------------------------------------------------ DomainAgent

def test_domain_agent_no_domain_returns_empty():
    assert asyncio.run(DomainAgent().gather(Target())) == []


def test_domain_agent_invalid_domain_returns_empty():
    assert asyncio.run(DomainAgent().gather(Target(domain="not a domain"))) == []


def test_domain_agent_whois_failure_returns_none(monkeypatch):
    import whois

    def boom(domain):
        raise RuntimeError("network down")

    monkeypatch.setattr(whois, "whois", boom)
    assert DomainAgent()._whois("example.com") is None


def test_domain_agent_crtsh_failure_returns_none(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeClient(_raising_get))
    result = asyncio.run(DomainAgent()._crtsh("example.com"))
    assert result is None


def test_domain_agent_mailbox_domain_skips_everything(monkeypatch):
    """Gmail/Yahoo/etc DNS/WHOIS is the provider's infra, never the target's —
    should return no findings at all, not just skip crt.sh."""
    agent = DomainAgent()
    called = {"whois": False, "dns": False, "crtsh": False}
    monkeypatch.setattr(agent, "_whois", lambda d: called.__setitem__("whois", True))
    monkeypatch.setattr(agent, "_dns", lambda d: called.__setitem__("dns", True) or [])

    async def fake_crtsh(d):
        called["crtsh"] = True
        return None

    monkeypatch.setattr(agent, "_crtsh", fake_crtsh)
    findings = asyncio.run(agent.gather(Target(email="x@gmail.com")))
    assert findings == []
    assert called == {"whois": False, "dns": False, "crtsh": False}


# ------------------------------------------------------------------ BreachAgent

def test_breach_agent_no_email_returns_empty():
    assert asyncio.run(BreachAgent().gather(Target())) == []


def test_breach_agent_network_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeClient(_raising_get))
    findings = asyncio.run(BreachAgent().gather(Target(email="x@example.com")))
    assert findings == []


def test_breach_agent_404_returns_no_known_breaches(monkeypatch):
    class FakeResp:
        status_code = 404

    async def _get(*a, **k):
        return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeClient(_get))
    findings = asyncio.run(BreachAgent().gather(Target(email="x@example.com")))
    assert len(findings) == 1
    assert findings[0].title == "No known breaches"


# ------------------------------------------------------------------- ImageAgent

def test_image_agent_no_path_returns_empty():
    assert asyncio.run(ImageAgent().gather(Target())) == []


def test_image_agent_missing_file_returns_explicit_finding():
    findings = asyncio.run(ImageAgent().gather(Target(image_path="/no/such/file.jpg")))
    assert len(findings) == 1
    assert findings[0].title == "Image path missing"


def test_image_agent_corrupt_file_returns_exif_read_failed(tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not a real image")
    findings = asyncio.run(ImageAgent().gather(Target(image_path=str(bad))))
    assert len(findings) == 1
    assert findings[0].title == "EXIF read failed"


def test_image_agent_valid_image_without_exif(tmp_path):
    from PIL import Image

    img_path = tmp_path / "plain.jpg"
    Image.new("RGB", (10, 10), color="red").save(img_path, format="JPEG")
    findings = asyncio.run(ImageAgent().gather(Target(image_path=str(img_path))))
    assert len(findings) == 1
    assert findings[0].title == "No EXIF data"


# ------------------------------------------------------------- SocialMediaAgent

def test_social_media_agent_no_candidates_returns_empty():
    assert asyncio.run(SocialMediaAgent().gather(Target())) == []


def test_social_media_probe_finding_carries_handle_for_correlation(monkeypatch):
    """canonical_handles() (entity_resolver) groups findings by data['handle'] --
    probe findings must carry it for cross-platform correlation to work."""
    agent = SocialMediaAgent()

    async def fake_probe(handle):
        return {"instagram": {"platform": "instagram", "url": "https://instagram.com/x",
                               "status": 200, "exists": True, "confidence": 60}}

    async def fake_none(handle):
        return None

    monkeypatch.setattr(agent, "_probe_existence", fake_probe)
    monkeypatch.setattr(agent, "_instagram", fake_none)
    monkeypatch.setattr(agent, "_reddit", fake_none)

    findings = asyncio.run(agent.gather(Target(username="targethandle")))
    assert len(findings) == 1
    assert findings[0].data["handle"] == "targethandle"


def test_social_media_head_probe_network_failure_handled():
    class FakeClient:
        async def get(self, url):
            raise RuntimeError("timeout")

    result = asyncio.run(SocialMediaAgent()._head(FakeClient(), "instagram", "http://example.com"))
    assert result["exists"] is False
    assert result["confidence"] == 0
    assert "error" in result


def test_social_media_instagram_blocked_returns_degraded_finding(monkeypatch):
    import instaloader

    class FakeProfile:
        @staticmethod
        def from_username(context, handle):
            raise RuntimeError("403 rate limited login checkpoint")

    monkeypatch.setattr(instaloader, "Profile", FakeProfile)
    finding = asyncio.run(SocialMediaAgent()._instagram("somebody"))
    assert finding is not None
    assert "blocked" in finding.title.lower()


def test_social_media_instagram_generic_failure_returns_none(monkeypatch):
    import instaloader

    class FakeProfile:
        @staticmethod
        def from_username(context, handle):
            raise RuntimeError("does not exist")

    monkeypatch.setattr(instaloader, "Profile", FakeProfile)
    result = asyncio.run(SocialMediaAgent()._instagram("somebody"))
    assert result is None


def test_social_media_reddit_no_credentials_returns_none():
    result = asyncio.run(SocialMediaAgent()._reddit("somebody"))
    assert result is None


# --------------------------------------------------------------- GitHubAgent

def test_github_agent_network_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeClient(_raising_get))
    findings = asyncio.run(GitHubAgent().gather(Target(username="somebody")))
    assert findings == []


def test_github_agent_non_200_returns_empty(monkeypatch):
    class FakeResp:
        status_code = 404

    async def _get(*a, **k):
        return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeClient(_get))
    findings = asyncio.run(GitHubAgent().gather(Target(username="somebody")))
    assert findings == []
