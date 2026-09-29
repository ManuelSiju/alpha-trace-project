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
    # portfolio / personal-site discovery
    assert any("portfolio" in q for q in queries)
    assert len(queries) <= WebAgent.MAX_QUERIES


def test_build_queries_derives_slug_from_email_local_part():
    agent = WebAgent()
    queries = agent._build_queries(Target(email="manuelsiju03@gmail.com"))
    # email local-part gets its own bare query even without a username field
    assert '"manuelsiju03"' in queries
    # and feeds portfolio-host discovery
    assert any("manuelsiju03" in q and "github.io" in q for q in queries)


def test_build_queries_skips_absent_fields():
    agent = WebAgent()
    queries = agent._build_queries(Target(username="soloqueryuser"))
    # username -> its own bare query + a portfolio-host discovery query
    assert '"soloqueryuser"' in queries
    assert any("portfolio" in q for q in queries)


def test_search_success_returns_finding():
    agent = WebAgent()
    agent._search_with_retry = lambda q: [{"title": "Hit", "href": "https://example.com"}]
    findings = asyncio.run(agent.gather(_target()))
    # name -> bare query + site:linkedin.com dork + portfolio discovery query
    assert len(findings) == len(agent._build_queries(_target()))
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
    n_queries = len(agent._build_queries(_target()))
    asyncio.run(agent.gather(_target()))
    assert call_count["n"] == n_queries  # first run: every query is a real search

    asyncio.run(agent.gather(_target()))
    assert call_count["n"] == n_queries  # second run: all served from cache, no new searches


def test_retry_recovers_from_transient_failure():
    # username-only target produces exactly one bare query plus one portfolio
    # query; force a single query via a lone email domain would still be 2, so
    # assert on the ceiling of one flaky query's retries rather than a hard
    # count to stay robust to the query set.
    agent = WebAgent()
    target = Target(username="soloqueryuser")
    queries = agent._build_queries(target)
    per_query_attempts: dict[str, int] = {}

    def _flaky(q):
        per_query_attempts[q] = per_query_attempts.get(q, 0) + 1
        if per_query_attempts[q] < 2:
            raise RuntimeError("transient")
        return [{"title": "Hit", "href": "https://example.com"}]

    agent._search = _flaky
    findings = asyncio.run(agent.gather(target))
    # each query retried once then succeeded (tenacity: 2 attempts)
    assert all(v == 2 for v in per_query_attempts.values())
    assert len(findings) == len(queries)
    assert all(f.title != "Web search unavailable" for f in findings)
