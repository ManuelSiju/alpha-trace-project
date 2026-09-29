from __future__ import annotations
from typing import List

import httpx
from loguru import logger

from core.agents.base_agent import BaseAgent
from core.models.schema import Target, Finding
from core.utils.validators import is_email
from core.utils.user_agent_rotator import default_headers


class BreachAgent(BaseAgent):
    name = "BreachAgent"
    category = "Breach Exposure"

    async def gather(self, target: Target) -> List[Finding]:
        if not target.email or not is_email(target.email):
            return []
        email = target.email.lower()
        url = f"https://api.xposedornot.com/v1/check-email/{email}"
        try:
            async with httpx.AsyncClient(timeout=15, headers=default_headers()) as c:
                r = await c.get(url)
        except Exception as e:
            logger.debug(f"xposedornot failed: {e}")
            return []

        if r.status_code == 404:
            return [Finding(
                category=self.category,
                source="xposedornot",
                title="No known breaches",
                content=f"{email} not present in XposedOrNot's indexed breaches.",
                confidence=70,
            )]
        if r.status_code != 200:
            return []

        try:
            data = r.json()
        except Exception:
            return []

        breaches = data.get("breaches", [])
        if isinstance(breaches, list) and breaches and isinstance(breaches[0], list):
            breaches = breaches[0]
        if not breaches:
            return [Finding(
                category=self.category,
                source="xposedornot",
                title="No breaches indexed",
                content=f"XposedOrNot returned empty breach list for {email}.",
                confidence=65,
            )]

        findings = [Finding(
            category=self.category,
            source="xposedornot",
            title=f"Exposed in {len(breaches)} breach(es)",
            content="Breaches: " + ", ".join(map(str, breaches[:30])),
            url="https://xposedornot.com",
            confidence=90,
            data={"breaches": breaches},
        )]

        # Richer detail pass: the breach-analytics endpoint returns per-breach
        # metadata (year, exposed data classes like passwords/phones) and any
        # associated paste dumps -- turns "exposed in N breaches" into "which
        # data of theirs leaked, and when", which is what actually matters for
        # an exposure assessment.
        analytics = await self._breach_analytics(email)
        if analytics:
            findings.append(analytics)
        return findings

    async def _breach_analytics(self, email: str) -> "Finding | None":
        url = f"https://api.xposedornot.com/v1/breach-analytics?email={email}"
        try:
            async with httpx.AsyncClient(timeout=15, headers=default_headers()) as c:
                r = await c.get(url)
                if r.status_code != 200:
                    return None
                data = r.json()
        except Exception as e:
            logger.debug(f"xposedornot analytics failed: {e}")
            return None

        exposed_classes: list[str] = []
        detailed = (data or {}).get("ExposedBreaches", {}).get("breaches_details", []) or []
        for b in detailed:
            xposed = b.get("xposed_data") or ""
            if xposed:
                exposed_classes.extend(str(xposed).split(";"))
        exposed_classes = sorted({c.strip() for c in exposed_classes if c.strip()})

        pastes = (data or {}).get("PastesSummary", {}) or {}
        paste_count = pastes.get("cnt") or 0

        if not exposed_classes and not paste_count:
            return None
        bits = []
        if exposed_classes:
            bits.append("exposed data types: " + ", ".join(exposed_classes[:20]))
        if paste_count:
            bits.append(f"{paste_count} associated paste dump(s)")
        return Finding(
            category=self.category,
            source="xposedornot:analytics",
            title="Breach exposure detail",
            content="; ".join(bits),
            url="https://xposedornot.com",
            confidence=85,
            data={"exposed_data_classes": exposed_classes, "paste_count": paste_count},
        )
