from __future__ import annotations
import asyncio
from typing import List, Dict, Any

import httpx
from loguru import logger

from core.agents.base_agent import BaseAgent
from core.models.schema import Target, Finding
from core.utils.user_agent_rotator import default_headers
from core.utils.validators import redact
from config.settings import settings


class SocialMediaAgent(BaseAgent):
    name = "SocialMediaAgent"
    category = "Social Media"

    async def gather(self, target: Target) -> List[Finding]:
        candidates = target.candidate_usernames()
        if not candidates:
            return []

        primary = candidates[0]
        findings: List[Finding] = []

        # Light HEAD probes; full scrapers loaded only if a hit appears
        existence = await self._probe_existence(primary)
        for plat, hit in existence.items():
            if hit["exists"]:
                findings.append(Finding(
                    category=self.category,
                    source=f"probe:{plat}",
                    title=f"{plat} profile probable for @{primary}",
                    content=f"{plat}: {hit['url']} (HTTP {hit['status']})",
                    url=hit["url"],
                    confidence=hit["confidence"],
                    data={**hit, "handle": primary},
                ))

        # Instagram via instaloader (lazy)
        ig = await self._instagram(primary)
        if ig:
            findings.append(ig)

        # Reddit via PRAW (lazy, needs keys)
        reddit = await self._reddit(primary)
        if reddit:
            findings.append(reddit)

        return findings

    async def _probe_existence(self, handle: str) -> Dict[str, Dict[str, Any]]:
        urls = {
            "instagram": f"https://www.instagram.com/{handle}/",
            "twitter": f"https://x.com/{handle}",
            "github": f"https://github.com/{handle}",
            "reddit": f"https://www.reddit.com/user/{handle}/",
            "youtube": f"https://www.youtube.com/@{handle}",
            "tiktok": f"https://www.tiktok.com/@{handle}",
            "medium": f"https://medium.com/@{handle}",
            "dev.to": f"https://dev.to/{handle}",
            "telegram": f"https://t.me/{handle}",
            "bluesky": f"https://bsky.app/profile/{handle}.bsky.social",
            "pinterest": f"https://www.pinterest.com/{handle}/",
            "keybase": f"https://keybase.io/{handle}",
        }
        out: Dict[str, Dict[str, Any]] = {}
        async with httpx.AsyncClient(timeout=10, headers=default_headers(), follow_redirects=True) as c:
            tasks = [self._head(c, plat, url) for plat, url in urls.items()]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, dict):
                    out[r["platform"]] = r
        return out

    async def _head(self, c: httpx.AsyncClient, plat: str, url: str) -> Dict[str, Any]:
        try:
            r = await c.get(url)
            status = r.status_code
            exists = status == 200 and len(r.text) > 1000
            confidence = 60 if exists else 20
            # Heuristic: pages that return 200 with login wall: lower confidence
            if exists and "login" in r.text.lower()[:5000] and plat in ("instagram", "facebook", "linkedin", "threads"):
                confidence = 45
            return {"platform": plat, "url": url, "status": status, "exists": exists, "confidence": confidence}
        except Exception as e:
            return {"platform": plat, "url": url, "status": -1, "exists": False, "confidence": 0, "error": str(e)}

    async def _instagram(self, handle: str) -> Finding | None:
        try:
            import instaloader
        except ImportError:
            return None
        loop = asyncio.get_running_loop()

        def _fetch() -> Dict[str, Any] | str | None:
            L = instaloader.Instaloader(quiet=True, download_pictures=False, download_videos=False,
                                        download_video_thumbnails=False, save_metadata=False)
            try:
                profile = instaloader.Profile.from_username(L.context, handle)
                return {
                    "username": profile.username,
                    "full_name": profile.full_name,
                    "biography": profile.biography,
                    "followers": profile.followers,
                    "followees": profile.followees,
                    "posts": profile.mediacount,
                    "is_private": profile.is_private,
                    "is_verified": profile.is_verified,
                    "external_url": profile.external_url,
                }
            except Exception as e:
                msg = str(e).lower()
                if "403" in msg or "login" in msg or "rate" in msg or "checkpoint" in msg:
                    return "blocked"
                logger.debug(f"instaloader failed for {redact(handle)}: {e}")
                return None

        data = await loop.run_in_executor(None, _fetch)
        if data == "blocked":
            return Finding(
                category=self.category,
                source="instagram",
                title=f"Instagram profile @{handle} likely exists (detail blocked)",
                content="HEAD probe returned 200 earlier; instaloader hit IG rate limit / login wall, profile detail unavailable.",
                url=f"https://www.instagram.com/{handle}/",
                confidence=50,
                data={"username": handle, "blocked": True},
            )
        if not data:
            return None
        return Finding(
            category=self.category,
            source="instagram",
            title=f"Instagram profile @{data['username']}",
            content=f"name={data['full_name']}; followers={data['followers']}; posts={data['posts']}; private={data['is_private']}; bio={data['biography'][:120] if data['biography'] else ''}",
            url=f"https://www.instagram.com/{data['username']}/",
            confidence=88,
            data=data,
        )

    async def _reddit(self, handle: str) -> Finding | None:
        if not (settings.REDDIT_CLIENT_ID and settings.REDDIT_CLIENT_SECRET):
            return None
        try:
            import praw
        except ImportError:
            return None
        loop = asyncio.get_running_loop()

        def _fetch() -> Dict[str, Any] | None:
            r = praw.Reddit(
                client_id=settings.REDDIT_CLIENT_ID,
                client_secret=settings.REDDIT_CLIENT_SECRET,
                user_agent=settings.REDDIT_USER_AGENT,
            )
            try:
                u = r.redditor(handle)
                _ = u.id  # force fetch; throws if not found
                return {
                    "name": u.name,
                    "id": u.id,
                    "link_karma": getattr(u, "link_karma", None),
                    "comment_karma": getattr(u, "comment_karma", None),
                    "created_utc": getattr(u, "created_utc", None),
                }
            except Exception as e:
                logger.debug(f"reddit lookup failed: {e}")
                return None

        data = await loop.run_in_executor(None, _fetch)
        if not data:
            return None
        return Finding(
            category=self.category,
            source="reddit",
            title=f"Reddit user u/{data['name']}",
            content=f"karma_link={data.get('link_karma')}; karma_comment={data.get('comment_karma')}",
            url=f"https://www.reddit.com/user/{data['name']}/",
            confidence=85,
            data=data,
        )
