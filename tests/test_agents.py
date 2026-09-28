from __future__ import annotations
import asyncio
import pytest

from core.models.schema import Target, Finding
from core.agents.email_agent import EmailAgent
from core.agents.phone_agent import PhoneAgent
from core.agents.base_agent import BaseAgent
from core.agents.orchestrator import Orchestrator


class DummyAgent(BaseAgent):
    name = "Dummy"
    category = "Test"

    async def gather(self, target):
        return [Finding(category=self.category, source="dummy", title="x", content="ok", confidence=80)]


class FailingAgent(BaseAgent):
    name = "Failer"
    category = "Test"

    async def gather(self, target):
        raise RuntimeError("boom")


class SlowAgent(BaseAgent):
    name = "Slow"
    category = "Test"

    async def gather(self, target):
        await asyncio.sleep(10)
        return [Finding(category=self.category, source="slow", title="late", content="x")]


class EmptyAgent(BaseAgent):
    name = "Empty"
    category = "Test"

    async def gather(self, target):
        return []


def test_email_pattern():
    a = EmailAgent()
    assert a._email_pattern("first.last") == "firstname.lastname"
    assert a._email_pattern("first_last") == "firstname_lastname"
    assert a._email_pattern("jamiecarter2004") == "name+year"
    assert a._email_pattern("zxy") == "custom"


def test_target_candidates():
    t = Target(email="jamiecarter2004@gmail.com", name="Jamie Carter")
    cands = t.candidate_usernames()
    assert "jamiecarter2004" in cands
    assert "jamiecarter" in cands
    assert "jamie.carter" in cands


def test_orchestrator_error_isolation():
    orch = Orchestrator([DummyAgent(), FailingAgent()], timeout=10)
    findings = asyncio.run(orch.run_all(Target(name="t")))
    assert len(findings) == 1
    assert findings[0].title == "x"


def test_phone_agent_invalid():
    t = Target(phone="not-a-phone")
    findings = asyncio.run(PhoneAgent().gather(t))
    assert findings
    assert findings[0].confidence <= 30


def test_orchestrator_timeout_returns_empty_for_that_agent_only():
    """TS-3: a slow agent exceeding AGENT_TIMEOUT doesn't fail the whole run."""
    orch = Orchestrator([DummyAgent(), SlowAgent()], timeout=0.05)
    findings = asyncio.run(orch.run_all(Target(name="t")))
    assert len(findings) == 1
    assert findings[0].title == "x"


def test_on_event_reports_dispatched_and_terminal_states():
    events: list[tuple] = []
    orch = Orchestrator([DummyAgent(), FailingAgent()], timeout=10)
    asyncio.run(orch.run_all(Target(name="t"), on_event=lambda *a: events.append(a)))
    assert ("Dummy", "dispatched") in events
    assert ("Dummy", "returned", 1) in events
    assert ("Failer", "dispatched") in events
    assert ("Failer", "failed") in events


def test_on_event_reports_timeout_as_failed():
    events: list[tuple] = []
    orch = Orchestrator([SlowAgent()], timeout=0.05)
    asyncio.run(orch.run_all(Target(name="t"), on_event=lambda *a: events.append(a)))
    assert ("Slow", "failed") in events


def test_on_event_reports_no_trail_for_clean_empty_result():
    events: list[tuple] = []
    orch = Orchestrator([EmptyAgent()], timeout=10)
    asyncio.run(orch.run_all(Target(name="t"), on_event=lambda *a: events.append(a)))
    assert ("Empty", "no_trail", 0) in events
