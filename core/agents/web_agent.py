from __future__ import annotations
import asyncio
from typing import List

from loguru import logger

from core.agents.base_agent import BaseAgent
from core.models.schema import Target, Finding
from core.utils.validators import redact


class WebAgent(BaseAgent):
    name = "WebAgent"
    category = "Web Presence"

    MAX_RESULTS = 12

    async def gather(self, target: Target) -> List[Finding]:
        try:
            from ddgs import DDGS  # type: ignore
        except ImportError:
            try:
                from duckduckgo_search import DDGS  # type: ignore
            except ImportError:
                logger.warning("ddgs (or duckduckgo-search) not installed")
                return []

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

        for q in queries[:3]:
            try:
                results = await loop.run_in_executor(None, self._search, q)
            except Exception as e:
                logger.debug(f"DDG search failed for {redact(q)}: {e}")
                continue

            if not results:
                continue

            top = results[: self.MAX_RESULTS]
            findings.append(Finding(
                category=self.category,
                source=f"duckduckgo:{q}",
                title=f"{len(top)} web result(s) for {q}",
                content=" | ".join(f"{r.get('title','')} -> {r.get('href','')}" for r in top[:5]),
                confidence=55,
                data={"query": q, "results": top},
            ))
        return findings

    def _search(self, query: str) -> list[dict]:
        try:
            from ddgs import DDGS  # type: ignore
        except ImportError:
            from duckduckgo_search import DDGS  # type: ignore
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=self.MAX_RESULTS))
