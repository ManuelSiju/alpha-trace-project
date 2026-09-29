from __future__ import annotations
import asyncio
from typing import List, Optional

import httpx
from loguru import logger

from core.agents.base_agent import BaseAgent
from core.models.schema import Target, Finding
from core.utils.validators import is_domain
from core.utils.user_agent_rotator import default_headers


class DomainAgent(BaseAgent):
    name = "DomainAgent"
    category = "Domain Info"

    async def gather(self, target: Target) -> List[Finding]:
        # Resolve target domain: explicit field, else email domain
        dom = target.domain
        if not dom and target.email and "@" in target.email:
            dom = target.email.split("@", 1)[1]
        if not dom or not is_domain(dom):
            return []
        # Mass-mailbox providers (gmail.com etc.) carry zero personal signal in
        # their own WHOIS/DNS/subdomain data — it's always the provider's
        # generic infrastructure, never the target's. EmailAgent already
        # reports the provider itself; skip this agent entirely rather than
        # burn a request cycle and dilute the LLM's context with Google's DNS.
        mailbox_only = {"gmail.com", "googlemail.com", "yahoo.com", "outlook.com",
                        "hotmail.com", "icloud.com", "protonmail.com", "proton.me"}
        if dom.lower() in mailbox_only:
            return []

        findings: List[Finding] = []
        loop = asyncio.get_running_loop()

        whois_data = await loop.run_in_executor(None, self._whois, dom)
        if whois_data:
            findings.append(whois_data)

        dns_data = await loop.run_in_executor(None, self._dns, dom)
        findings.extend(dns_data)

        sub = await self._crtsh(dom)
        if sub:
            findings.append(sub)

        return findings

    def _whois(self, domain: str) -> Optional[Finding]:
        try:
            import whois  # python-whois
        except ImportError:
            logger.warning("python-whois not installed")
            return None
        try:
            w = whois.whois(domain)
            data = {k: str(v) for k, v in dict(w).items() if v}
            content = "; ".join(f"{k}={data[k]}" for k in list(data)[:8])
            return Finding(
                category=self.category,
                source="whois",
                title=f"WHOIS for {domain}",
                content=content[:1000],
                confidence=75,
                data=data,
            )
        except Exception as e:
            logger.debug(f"whois failed: {e}")
            return None

    def _dns(self, domain: str) -> List[Finding]:
        try:
            import dns.resolver
        except ImportError:
            logger.warning("dnspython not installed")
            return []
        out: List[Finding] = []
        resolver = dns.resolver.Resolver()
        resolver.timeout = 5
        resolver.lifetime = 8
        records = {}
        for rtype in ("A", "AAAA", "MX", "NS", "TXT"):
            try:
                answers = resolver.resolve(domain, rtype)
                records[rtype] = [str(a) for a in answers]
            except Exception:
                continue
        if records:
            content = "; ".join(f"{k}={','.join(v[:3])}" for k, v in records.items())
            out.append(Finding(
                category=self.category,
                source="dns",
                title=f"DNS records for {domain}",
                content=content,
                confidence=90,
                data=records,
            ))
        return out

    async def _crtsh(self, domain: str) -> Optional[Finding]:
        url = f"https://crt.sh/?q=%25.{domain}&output=json"
        try:
            async with httpx.AsyncClient(timeout=20, headers=default_headers()) as c:
                r = await c.get(url)
                if r.status_code != 200:
                    return None
                rows = r.json()
        except Exception as e:
            logger.debug(f"crt.sh failed: {e}")
            return None
        subs = sorted({row.get("name_value", "").strip() for row in rows if row.get("name_value")})
        subs = [s for s in subs if s and "*" not in s]
        if not subs:
            return None
        return Finding(
            category=self.category,
            source="crt.sh",
            title=f"{len(subs)} subdomain entries",
            content=", ".join(subs[:30]),
            url=url,
            confidence=80,
            data={"subdomains": subs[:200]},
        )
