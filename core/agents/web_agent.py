from __future__ import annotations
import asyncio
import json
from typing import List, Optional

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from core.agents.base_agent import BaseAgent
from core.models.schema import Target, Finding
from core.utils.validators import redact
from config.settings import settings


class WebAgent(BaseAgent):
    name = "WebAgent"
    category = "Web Presence"

    MAX_RESULTS = 12
    SEARCH_TIMEOUT = 20  # seconds; shared budget per query (ddgs "auto" backend already
                          # fans out across multiple search engines within one call)

    async def gather(self, target: Target) -> List[Finding]:
        try:
            from ddgs import DDGS  # noqa: F401  (import check only)
        except ImportError:
            try:
                from duckduckgo_search import DDGS  # noqa: F401
            except ImportError:
                logger.warning("ddgs (or duckduckgo-search) not installed")
                return [self._unavailable("the ddgs search library is not installed")]

        queries: List[str] = []
        if target.email:
            queries.append(f'"{target.email}"')
        if target.name:
            queries.append(f'"{target.name}"')
        if target.username:
            queries.append(f'"{target.username}"')
        if not queries:
            return []

        findings: List[Finding] = []
        loop = asyncio.get_running_loop()
        any_result = False

        for q in queries[:3]:
            results = self._cache_get(q)
            if results is None:
                try:
                    results = await asyncio.wait_for(
                        loop.run_in_executor(None, self._search_with_retry, q),
                        timeout=self.SEARCH_TIMEOUT,
                    )
                    self._cache_put(q, results)
                except Exception as e:
                    logger.debug(f"web search failed for {redact(q)}: {e}")
                    continue

            if not results:
                continue
            any_result = True
            top = results[: self.MAX_RESULTS]
            findings.append(Finding(
                category=self.category,
                source=f"duckduckgo:{q}",
                title=f"{len(top)} web result(s) for {q}",
                content=" | ".join(f"{r.get('title','')} -> {r.get('href','')}" for r in top[:5]),
                confidence=55,
                data={"query": q, "results": top},
            ))

        if not any_result:
            findings.append(self._unavailable("no search engine returned results (all backends failed, timed out, or returned nothing)"))
        return findings

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=4), reraise=True)
    def _search_with_retry(self, query: str) -> list[dict]:
        return self._search(query)

    def _search(self, query: str) -> list[dict]:
        try:
            from ddgs import DDGS  # type: ignore
        except ImportError:
            from duckduckgo_search import DDGS  # type: ignore
        with DDGS() as ddgs:
            return list(ddgs.text(query, backend="auto", max_results=self.MAX_RESULTS))

    def _unavailable(self, reason: str) -> Finding:
        return Finding(
            category=self.category,
            source="web-search",
            title="Web search unavailable",
            content=f"Could not complete a web search: {reason}.",
            confidence=0,
        )

    def _cache_key(self, query: str) -> str:
        return f"websearch:{query}"

    def _cache_get(self, query: str) -> Optional[list[dict]]:
        cache = getattr(self, "cache", None)
        if not cache:
            return None
        raw = cache.cache_get(self._cache_key(query))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    def _cache_put(self, query: str, results: list[dict]) -> None:
        cache = getattr(self, "cache", None)
        if not cache or results is None:
            return
        try:
            cache.cache_put(self._cache_key(query), json.dumps(results).encode("utf-8"), ttl=settings.CACHE_TTL)
        except (TypeError, ValueError):
            pass
