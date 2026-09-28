from __future__ import annotations
import asyncio

from core.agents.web_agent import WebAgent
from core.models.schema import Target
from core.memory.session_store import SessionStore


def _target():
    return Target(name="Jamie Carter")


def test_no_identifiers_returns_empty():
    agent = WebAgent()
    findings = asyncio.run(agent.gather(Target()))
    assert findings == []


def test_search_success_returns_finding():
    agent = WebAgent()
    agent._search_with_retry = lambda q: [{"title": "Hit", "href": "https://example.com"}]
    findings = asyncio.run(agent.gather(_target()))
    assert len(findings) == 1
    assert "web result" in findings[0].title
    assert findings[0].confidence == 55


def test_all_backends_fail_returns_explicit_unavailable_finding():
    def _boom(q):
        raise RuntimeError("all engines down")

    agent = WebAgent()
    agent._search_with_retry = _boom
    findings = asyncio.run(agent.gather(_target()))
    assert len(findings) == 1
    assert findings[0].title == "Web search unavailable"
    assert findings[0].confidence == 0


def test_empty_results_from_all_queries_returns_unavailable():
    agent = WebAgent()
    agent._search_with_retry = lambda q: []
    findings = asyncio.run(agent.gather(_target()))
    assert len(findings) == 1
    assert findings[0].title == "Web search unavailable"


def test_cache_hit_skips_real_search(tmp_path):
    store = SessionStore(base_dir=tmp_path)
    store.new_session(Target(name="t"))

    agent = WebAgent()
    agent.cache = store
    call_count = {"n": 0}

    def _search(q):
        call_count["n"] += 1
        return [{"title": "Hit", "href": "https://example.com"}]

    agent._search_with_retry = _search
    asyncio.run(agent.gather(_target()))
    assert call_count["n"] == 1  # first call: real search, then cached

    asyncio.run(agent.gather(_target()))
    assert call_count["n"] == 1  # second call: served from cache, no new search


def test_retry_recovers_from_transient_failure():
    agent = WebAgent()
    attempts = {"n": 0}

    def _flaky(q):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("transient")
        return [{"title": "Hit", "href": "https://example.com"}]

    agent._search = _flaky
    findings = asyncio.run(agent.gather(_target()))
    assert attempts["n"] == 2
    assert len(findings) == 1
    assert findings[0].title != "Web search unavailable"
