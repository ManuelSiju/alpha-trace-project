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
                            # blog = often a personal portfolio URL; twitter_username
                            # = a directly-linked cross-platform handle; company/email
                            # are self-published. These are the highest-value fields on
                            # the profile and were previously fetched but never surfaced.
                            extra = []
                            if d.get("blog"):
                                extra.append(f"website={d['blog']}")
                            if d.get("twitter_username"):
                                extra.append(f"twitter=@{d['twitter_username']}")
                            if d.get("company"):
                                extra.append(f"company={d['company']}")
                            if d.get("email"):
                                extra.append(f"email={d['email']}")
                            extra_str = ("; " + "; ".join(extra)) if extra else ""
                            findings.append(Finding(
                                category=self.category,
                                source="github:user",
                                title=f"GitHub user @{val}",
                                content=f"name={d.get('name')}; bio={d.get('bio')}; repos={d.get('public_repos')}; followers={d.get('followers')}; location={d.get('location')}{extra_str}",
                                url=d.get("html_url"),
                                confidence=92,
                                data={**d, "handle": val},
                            ))
                            # A public website/blog on the profile is a strong lead in
                            # its own right (usually the portfolio) -- emit it separately
                            # so it lands in Connections and can be searched further.
                            if d.get("blog"):
                                blog = d["blog"]
                                if not blog.startswith("http"):
                                    blog = "https://" + blog
                                findings.append(Finding(
                                    category=self.category,
                                    source="github:website",
                                    title=f"Personal website linked from GitHub @{val}",
                                    content=f"Self-published website: {blog}",
                                    url=blog,
                                    confidence=80,
                                    data={"handle": val, "website": blog},
                                ))
                            # Confirmed real account -> follow the graph: repos
                            # (skills + linked sites), commit author emails (the
                            # real email behind the account), and who they follow
                            # (a higher-signal network than random followers).
                            login = d.get("login") or val
                            findings.extend(await self._deep_dive(c, login))
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

    async def _deep_dive(self, c: httpx.AsyncClient, login: str) -> List[Finding]:
        out: List[Finding] = []
        for fn in (self._repos, self._commit_emails, self._following):
            try:
                out.extend(await fn(c, login))
            except Exception as e:
                logger.debug(f"github deep-dive {fn.__name__} failed: {e}")
        return out

    async def _repos(self, c: httpx.AsyncClient, login: str) -> List[Finding]:
        r = await c.get(f"{self.BASE}/users/{login}/repos",
                        params={"sort": "pushed", "per_page": "20", "type": "owner"})
        if r.status_code != 200:
            return []
        repos = r.json() or []
        if not repos:
            return []
        out: List[Finding] = []
        langs = sorted({rp.get("language") for rp in repos if rp.get("language")})
        topics: list[str] = []
        for rp in repos:
            topics.extend(rp.get("topics") or [])
        topics = sorted(set(topics))
        top = sorted(repos, key=lambda rp: rp.get("stargazers_count", 0), reverse=True)[:8]
        repo_lines = [
            f"{rp.get('name')}"
            + (f" ({rp.get('language')})" if rp.get("language") else "")
            + (f" ★{rp.get('stargazers_count')}" if rp.get("stargazers_count") else "")
            + (f" - {rp.get('description')[:80]}" if rp.get("description") else "")
            for rp in top
        ]
        out.append(Finding(
            category=self.category,
            source="github:repos",
            title=f"{len(repos)} public repo(s) for @{login}",
            content=(f"Languages: {', '.join(langs)}. " if langs else "")
                    + (f"Topics/skills: {', '.join(topics[:20])}. " if topics else "")
                    + "Notable: " + "; ".join(repo_lines),
            url=f"https://github.com/{login}?tab=repositories",
            confidence=75,
            data={"handle": login, "languages": langs, "topics": topics,
                  "repos": [{"name": rp.get("name"), "url": rp.get("html_url"),
                             "homepage": rp.get("homepage"), "stars": rp.get("stargazers_count"),
                             "language": rp.get("language"), "description": rp.get("description")}
                            for rp in top]},
        ))
        # Repo homepage fields are frequently the person's live portfolio/project
        # site -- surface each distinct one as its own lead.
        seen = set()
        for rp in repos:
            hp = (rp.get("homepage") or "").strip()
            if hp and hp.startswith("http") and hp not in seen:
                seen.add(hp)
                out.append(Finding(
                    category=self.category,
                    source="github:repo-site",
                    title=f"Project/portfolio site from @{login}'s repo '{rp.get('name')}'",
                    content=f"Linked site: {hp}",
                    url=hp,
                    confidence=65,
                    data={"handle": login, "website": hp, "repo": rp.get("name")},
                ))
        return out

    async def _commit_emails(self, c: httpx.AsyncClient, login: str) -> List[Finding]:
        # Public push events expose commit author emails -- often the person's
        # real email behind a GitHub account. GitHub's own noreply addresses are
        # filtered out (they carry no new info).
        r = await c.get(f"{self.BASE}/users/{login}/events/public", params={"per_page": "100"})
        if r.status_code != 200:
            return []
        events = r.json() or []
        emails: dict[str, str] = {}
        for ev in events:
            if ev.get("type") != "PushEvent":
                continue
            for commit in (ev.get("payload", {}) or {}).get("commits", []) or []:
                author = commit.get("author", {}) or {}
                email = (author.get("email") or "").strip().lower()
                name = author.get("name") or ""
                if email and "noreply.github.com" not in email and "@" in email:
                    emails.setdefault(email, name)
        if not emails:
            return []
        listed = "; ".join(f"{e}" + (f" ({n})" if n else "") for e, n in list(emails.items())[:10])
        return [Finding(
            category=self.category,
            source="github:commit-emails",
            title=f"{len(emails)} email(s) from @{login}'s public commits",
            content=f"Author emails found in public commit history: {listed}",
            confidence=78,
            data={"handle": login, "emails": list(emails.keys())},
        )]

    async def _following(self, c: httpx.AsyncClient, login: str) -> List[Finding]:
        r = await c.get(f"{self.BASE}/users/{login}/following", params={"per_page": "15"})
        if r.status_code != 200:
            return []
        users = r.json() or []
        if not users:
            return []
        logins = [u.get("login") for u in users if u.get("login")]
        return [Finding(
            category=self.category,
            source="github:following",
            title=f"@{login} follows {len(logins)} account(s)",
            content="Follows (often real-world colleagues/collaborators): "
                    + ", ".join(logins[:15]),
            url=f"https://github.com/{login}?tab=following",
            confidence=50,
            data={"handle": login, "following": logins},
        )]
