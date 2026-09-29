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
    MAX_QUERIES = 12
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

        queries = self._build_queries(target)
        if not queries:
            return []

        # Run the whole query set concurrently -- more coverage without more
        # wall-clock time, since ddgs "auto" already fans out per-query and
        # each query gets its own timeout/retry/cache independently.
        results_by_query = await asyncio.gather(*[self._run_one_query(q) for q in queries])

        findings: List[Finding] = []
        any_result = False
        for q, results in results_by_query:
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

    def _build_queries(self, target: Target) -> List[str]:
        """Every identifier given gets its own query, plus a couple of
        combined/targeted ones for disambiguation and platform discovery.
        The `site:linkedin.com` query asks the search engine what it has
        already indexed -- it never contacts linkedin.com itself, so it
        doesn't carry the direct-scraping ToS risk that excludes LinkedIn
        from the HTTP existence-probe list."""
        queries: List[str] = []
        if target.email:
            queries.append(f'"{target.email}"')
            # Email local-part often equals a handle/portfolio slug even when
            # the username field wasn't given (e.g. manuelsiju03@ -> a site
            # titled/hosted under "manuelsiju03").
            local = target.email.split("@", 1)[0]
            if local and local != (target.username or ""):
                queries.append(f'"{local}"')
        if target.name:
            queries.append(f'"{target.name}"')
        if target.username:
            queries.append(f'"{target.username}"')
        if target.phone:
            queries.append(f'"{target.phone}"')
        if target.domain:
            queries.append(f'"{target.domain}"')
        if target.name and target.company:
            queries.append(f'"{target.name}" "{target.company}"')
        if target.name and target.location:
            queries.append(f'"{target.name}" "{target.location}"')
        if target.name:
            queries.append(f'"{target.name}" site:linkedin.com')
        # Portfolio / personal-site discovery: pair the strongest name-ish
        # token with intent keywords so a self-hosted portfolio (a very common
        # thing for the people this tool is pointed at) actually surfaces
        # instead of only their social profiles.
        slug = target.username or (target.email.split("@", 1)[0] if target.email else None)
        if target.name:
            queries.append(f'"{target.name}" (portfolio OR resume OR CV OR "personal website")')
        if slug:
            queries.append(f'{slug} (portfolio OR github.io OR vercel.app OR netlify.app)')
        return queries[: self.MAX_QUERIES]

    async def _run_one_query(self, q: str) -> tuple[str, Optional[list[dict]]]:
        results = self._cache_get(q)
        if results is None:
            loop = asyncio.get_running_loop()
            try:
                results = await asyncio.wait_for(
                    loop.run_in_executor(None, self._search_with_retry, q),
                    timeout=self.SEARCH_TIMEOUT,
                )
                self._cache_put(q, results)
            except Exception as e:
                logger.debug(f"web search failed for {redact(q)}: {e}")
                results = None
        return q, results

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
