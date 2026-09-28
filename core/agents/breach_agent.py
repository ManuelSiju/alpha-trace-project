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

        return [Finding(
            category=self.category,
            source="xposedornot",
            title=f"Exposed in {len(breaches)} breach(es)",
            content="Breaches: " + ", ".join(map(str, breaches[:30])),
            url="https://xposedornot.com",
            confidence=90,
            data={"breaches": breaches},
        )]
