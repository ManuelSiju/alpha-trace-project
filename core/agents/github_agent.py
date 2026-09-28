from __future__ import annotations
from typing import List

import httpx
from loguru import logger

from core.agents.base_agent import BaseAgent
from core.models.schema import Target, Finding
from core.utils.user_agent_rotator import default_headers
from core.utils.validators import redact


class GitHubAgent(BaseAgent):
    name = "GitHubAgent"
    category = "GitHub"

    BASE = "https://api.github.com"

    async def gather(self, target: Target) -> List[Finding]:
        queries: list[tuple[str, str]] = []
        for u in target.candidate_usernames()[:3]:
            queries.append(("user", u))
        if target.email:
            queries.append(("email_search", target.email))
        if target.name:
            queries.append(("name_search", target.name))

        findings: List[Finding] = []
        headers = {**default_headers(), "Accept": "application/vnd.github+json"}
        async with httpx.AsyncClient(timeout=15, headers=headers) as c:
            for kind, val in queries:
                try:
                    if kind == "user":
                        r = await c.get(f"{self.BASE}/users/{val}")
                        if r.status_code == 200:
                            d = r.json()
                            findings.append(Finding(
                                category=self.category,
                                source="github:user",
                                title=f"GitHub user @{val}",
                                content=f"name={d.get('name')}; bio={d.get('bio')}; repos={d.get('public_repos')}; followers={d.get('followers')}; location={d.get('location')}",
                                url=d.get("html_url"),
                                confidence=92,
                                data=d,
                            ))
                    elif kind == "email_search":
                        r = await c.get(f"{self.BASE}/search/users", params={"q": f"{val} in:email"})
                        if r.status_code == 200:
                            items = r.json().get("items", [])
                            if items:
                                findings.append(Finding(
                                    category=self.category,
                                    source="github:search-email",
                                    title=f"{len(items)} GitHub user(s) matching email",
                                    content=", ".join(i["login"] for i in items[:5]),
                                    confidence=70,
                                    data={"items": items[:5]},
                                ))
                    elif kind == "name_search":
                        r = await c.get(f"{self.BASE}/search/users", params={"q": val})
                        if r.status_code == 200:
                            items = r.json().get("items", [])
                            if items:
                                findings.append(Finding(
                                    category=self.category,
                                    source="github:search-name",
                                    title=f"{len(items)} GitHub user(s) matching name",
                                    content=", ".join(i["login"] for i in items[:5]),
                                    confidence=55,
                                    data={"items": items[:5]},
                                ))
                except Exception as e:
                    logger.debug(f"github query failed {kind}={redact(val)}: {e}")
        return findings
