from __future__ import annotations
from typing import List

from loguru import logger

from core.agents.base_agent import BaseAgent
from core.models.schema import Target, Finding


class PeopleSearchAgent(BaseAgent):
    """Public-records stub. India-focused gentle sources only.

    Real scraping of MCA / eCourts / state property portals violates ToS and
    requires per-portal anti-bot handling. This stub queries archive.org's
    wayback for past indexing of person+location strings, which is legal and
    cheap.
    """
    name = "PeopleSearchAgent"
    category = "Public Records"

    async def gather(self, target: Target) -> List[Finding]:
        if not target.name:
            return []
        try:
            import httpx
            from core.utils.user_agent_rotator import default_headers
        except ImportError:
            return []

        url = "https://archive.org/wayback/available"
        candidates = [target.name]
        if target.location:
            candidates.append(f"{target.name} {target.location}")

        findings: List[Finding] = []
        async with httpx.AsyncClient(timeout=15, headers=default_headers()) as c:
            for q in candidates:
                try:
                    r = await c.get(url, params={"url": f"https://www.google.com/search?q={q}"})
                    if r.status_code == 200:
                        d = r.json()
                        closest = (d or {}).get("archived_snapshots", {}).get("closest")
                        if closest and closest.get("available"):
                            findings.append(Finding(
                                category=self.category,
                                source="wayback",
                                title=f"Archived search snapshot for '{q}'",
                                content=f"Snapshot date: {closest.get('timestamp')}",
                                url=closest.get("url"),
                                confidence=40,
                                data=closest,
                            ))
                except Exception as e:
                    logger.debug(f"wayback failed: {e}")
        return findings
