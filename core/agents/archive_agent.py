from __future__ import annotations
import asyncio
from typing import List, Optional

import httpx
from loguru import logger

from core.agents.base_agent import BaseAgent
from core.models.schema import Target, Finding
from core.utils.validators import is_domain
from core.utils.user_agent_rotator import default_headers

# Public Wayback Machine CDX index — lists every URL the Internet Archive has
# ever captured under a host, including pages long since deleted from the live
# site. No key, no login, fully public, ToS-clean.
CDX_API = "http://web.archive.org/cdx/search/cdx"


class ArchiveAgent(BaseAgent):
    name = "ArchiveAgent"
    category = "Archived Web"

    MAX_SNAPSHOTS = 40

    async def gather(self, target: Target) -> List[Finding]:
        # Mine the archive for any domain we have: an explicit domain, or the
        # host of a custom-domain email (mailbox providers are skipped -- their
        # archive is the provider's, not the target's).
        domains = self._candidate_domains(target)
        if not domains:
            return []

        findings: List[Finding] = []
        results = await asyncio.gather(*[self._mine(d) for d in domains])
        for f in results:
            if f:
                findings.append(f)
        return findings

    def _candidate_domains(self, target: Target) -> List[str]:
        mailbox = {"gmail.com", "googlemail.com", "yahoo.com", "outlook.com",
                   "hotmail.com", "live.com", "icloud.com", "me.com",
                   "protonmail.com", "proton.me"}
        out: List[str] = []
        if target.domain and is_domain(target.domain):
            out.append(target.domain.lower())
        if target.email and "@" in target.email:
            dom = target.email.split("@", 1)[1].lower()
            if is_domain(dom) and dom not in mailbox and dom not in out:
                out.append(dom)
        return out

    async def _mine(self, domain: str) -> Optional[Finding]:
        params = {
            "url": f"{domain}/*",
            "output": "json",
            "collapse": "urlkey",
            "limit": str(self.MAX_SNAPSHOTS),
            "fl": "original,timestamp,statuscode",
        }
        try:
            async with httpx.AsyncClient(timeout=20, headers=default_headers(), follow_redirects=True) as c:
                r = await c.get(CDX_API, params=params)
                if r.status_code != 200:
                    return None
                rows = r.json()
        except Exception as e:
            logger.debug(f"wayback CDX failed: {e}")
            return None

        # First row is the header (["original","timestamp","statuscode"]).
        if not rows or len(rows) < 2:
            return None
        data_rows = rows[1:]
        urls = []
        for row in data_rows:
            original = row[0] if row else None
            if original and original not in urls:
                urls.append(original)

        if not urls:
            return None
        return Finding(
            category=self.category,
            source="wayback-cdx",
            title=f"{len(urls)} archived page(s) for {domain}",
            content="Historically archived URLs (may include deleted pages): "
                    + ", ".join(urls[:15]),
            url=f"https://web.archive.org/web/*/{domain}",
            confidence=70,
            data={"domain": domain, "archived_urls": urls},
        )
