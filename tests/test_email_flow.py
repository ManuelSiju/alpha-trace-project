from __future__ import annotations
import asyncio
import pytest

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
