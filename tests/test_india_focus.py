from __future__ import annotations
import asyncio

from core.agents.web_agent import WebAgent
from core.agents.phone_agent import PhoneAgent
from core.models.schema import Target
from config.settings import settings


def test_web_queries_include_india_dorks_when_region_in(monkeypatch):
    monkeypatch.setattr(settings, "REGION_FOCUS", "IN")
    queries = WebAgent()._build_queries(Target(name="Arjun Nair"))
    assert any("naukri.com" in q for q in queries)
    assert any("India" in q for q in queries)


def test_web_queries_omit_india_dorks_when_region_neutral(monkeypatch):
    monkeypatch.setattr(settings, "REGION_FOCUS", "")
    queries = WebAgent()._build_queries(Target(name="Arjun Nair"))
    assert not any("naukri.com" in q for q in queries)


def test_bare_indian_mobile_parses_with_in_default(monkeypatch):
    monkeypatch.setattr(settings, "REGION_FOCUS", "IN")
    # a bare 10-digit Indian mobile (no +91) should parse+validate as India
    findings = asyncio.run(PhoneAgent().gather(Target(phone="9876543210")))
    assert findings
    f = findings[0]
    assert "India" in f.content
    assert f.data.get("valid") is True


def test_bare_number_region_neutral_may_not_validate(monkeypatch):
    monkeypatch.setattr(settings, "REGION_FOCUS", "")
    # with no default region, a bare national number can't be attributed to a
    # country -- should not crash, just parse-fail or come back invalid
    findings = asyncio.run(PhoneAgent().gather(Target(phone="9876543210")))
    assert findings  # returns a finding either way, never raises
