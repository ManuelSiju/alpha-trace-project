from __future__ import annotations
import asyncio
from typing import List, Optional

import httpx
from loguru import logger

from core.agents.base_agent import BaseAgent
from core.models.schema import Target, Finding
from core.utils.user_agent_rotator import default_headers

# SEC EDGAR full-text search: free, public, no key. Indexes US corporate/
# securities filings (registrations, insider transactions, fund docs). A name
# or company appearing here is a genuine public business record -- officers,
# directors, fund managers, company principals surface this way.


class RegistryAgent(BaseAgent):
    name = "RegistryAgent"
    category = "Public Records"

    MAX_HITS = 10

    async def gather(self, target: Target) -> List[Finding]:
        terms: List[tuple[str, str]] = []
        if target.name:
            terms.append(("name", target.name))
        if target.company:
            terms.append(("company", target.company))
        if not terms:
            return []

        results = await asyncio.gather(*[self._edgar(label, q) for label, q in terms])
        return [f for f in results if f]

    async def _edgar(self, label: str, query: str) -> Optional[Finding]:
        # EDGAR's real full-text endpoint is efts.sec.gov/LATEST/search-index;
        # it wants a descriptive User-Agent (SEC policy) and returns JSON hits.
        url = "https://efts.sec.gov/LATEST/search-index"
        headers = {**default_headers(), "User-Agent": "alpha-tracer OSINT research contact@example.com"}
        try:
            async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as c:
                r = await c.get(url, params={"q": f'"{query}"'})
                if r.status_code != 200:
                    return None
                data = r.json()
        except Exception as e:
            logger.debug(f"EDGAR search failed: {e}")
            return None

        hits = (((data or {}).get("hits") or {}).get("hits")) or []
        if not hits:
            return None
        entries = []
        for h in hits[: self.MAX_HITS]:
            src = h.get("_source", {}) or {}
            display = src.get("display_names") or []
            form = src.get("file_type") or src.get("root_form") or ""
            who = ", ".join(display) if display else "(filer)"
            entries.append(f"{who} [{form}]")

        return Finding(
            category=self.category,
            source="sec-edgar",
            title=f"{len(hits)} SEC EDGAR filing hit(s) matching {label}",
            content="US securities/corporate filings mentioning the "
                    f"{label}: " + "; ".join(entries[:8]),
            url=f"https://efts.sec.gov/LATEST/search-index?q=%22{query.replace(' ', '+')}%22",
            confidence=55,
            data={"query": query, "hit_count": len(hits), "entries": entries},
        )
