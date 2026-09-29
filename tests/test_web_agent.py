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


def test_build_queries_uses_every_identifier_provided():
    agent = WebAgent()
    target = Target(
        email="jamie@example.com", name="Jamie Carter", username="jcarter",
        phone="+15551234567", domain="example.com", company="Example Corp",
        location="Metropolis",
    )
    queries = agent._build_queries(target)

    assert '"jamie@example.com"' in queries
    assert '"Jamie Carter"' in queries
    assert '"jcarter"' in queries
    assert '"+15551234567"' in queries
    assert '"example.com"' in queries
    assert '"Jamie Carter" "Example Corp"' in queries
    assert '"Jamie Carter" "Metropolis"' in queries
    assert '"Jamie Carter" site:linkedin.com' in queries
    assert len(queries) <= WebAgent.MAX_QUERIES


def test_build_queries_skips_absent_fields():
    agent = WebAgent()
    queries = agent._build_queries(Target(username="soloqueryuser"))
    assert queries == ['"soloqueryuser"']


def test_search_success_returns_finding():
    agent = WebAgent()
    agent._search_with_retry = lambda q: [{"title": "Hit", "href": "https://example.com"}]
    findings = asyncio.run(agent.gather(_target()))
    # name -> its own query + a site:linkedin.com dork (queries the search
    # engine's index, never linkedin.com itself)
    assert len(findings) == 2
    assert all("web result" in f.title for f in findings)
    assert all(f.confidence == 55 for f in findings)


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
    assert call_count["n"] == 2  # name query + linkedin dork, first run: both real searches

    asyncio.run(agent.gather(_target()))
    assert call_count["n"] == 2  # second run: both served from cache, no new searches


def test_retry_recovers_from_transient_failure():
    # A single-query target (email only -- no name, so no linkedin dork added)
    # keeps this deterministic: concurrent queries would share the mutable
    # `attempts` counter and race.
    agent = WebAgent()
    target = Target(email="jamie@example.com")
    attempts = {"n": 0}

    def _flaky(q):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("transient")
        return [{"title": "Hit", "href": "https://example.com"}]

    agent._search = _flaky
    findings = asyncio.run(agent.gather(target))
    assert attempts["n"] == 2
    assert len(findings) == 1
    assert findings[0].title != "Web search unavailable"
