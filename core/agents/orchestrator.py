from __future__ import annotations
import asyncio
from typing import List, Dict, Type

from loguru import logger

from config.settings import settings
from core.models.schema import Target, Finding
from core.agents.base_agent import BaseAgent


class Orchestrator:
    """Fan-out runner. Each agent gets a timeout; errors isolated per-agent."""

    def __init__(self, agents: List[BaseAgent], timeout: int | None = None):
        self.agents = agents
        self.timeout = timeout or settings.AGENT_TIMEOUT

    async def run_all(self, target: Target) -> List[Finding]:
        if not self.agents:
            return []

        sem = asyncio.Semaphore(settings.MAX_CONCURRENT_REQUESTS)

        async def _bounded(agent: BaseAgent) -> List[Finding]:
            async with sem:
                try:
                    return await asyncio.wait_for(agent.run(target), timeout=self.timeout)
                except asyncio.TimeoutError:
                    logger.warning(f"[{agent.name}] timeout after {self.timeout}s")
                    return []

        results = await asyncio.gather(*[_bounded(a) for a in self.agents], return_exceptions=False)
        flat: List[Finding] = []
        for r in results:
            flat.extend(r)
        return flat

    def summary(self) -> Dict[str, str]:
        return {a.name: (a.last_error or "ok") for a in self.agents}


def build_default_agents() -> List[BaseAgent]:
    """Construct enabled agents based on settings flags."""
    from core.agents.email_agent import EmailAgent
    from core.agents.username_agent import UsernameAgent
    from core.agents.phone_agent import PhoneAgent
    from core.agents.domain_agent import DomainAgent
    from core.agents.social_media_agent import SocialMediaAgent
    from core.agents.github_agent import GitHubAgent
    from core.agents.web_agent import WebAgent
    from core.agents.breach_agent import BreachAgent
    from core.agents.image_agent import ImageAgent
    from core.agents.people_search_agent import PeopleSearchAgent

    pool: List[BaseAgent] = []
    if settings.ENABLE_EMAIL_AGENT:
        pool.append(EmailAgent())
    if settings.ENABLE_USERNAME_AGENT:
        pool.append(UsernameAgent())
    if settings.ENABLE_PHONE_AGENT:
        pool.append(PhoneAgent())
    if settings.ENABLE_DOMAIN_AGENT:
        pool.append(DomainAgent())
    if settings.ENABLE_SOCIAL_MEDIA_AGENT:
        pool.append(SocialMediaAgent())
    if settings.ENABLE_GITHUB_AGENT:
        pool.append(GitHubAgent())
    if settings.ENABLE_WEB_AGENT:
        pool.append(WebAgent())
    if settings.ENABLE_BREACH_AGENT:
        pool.append(BreachAgent())
    if settings.ENABLE_IMAGE_AGENT:
        pool.append(ImageAgent())
    if settings.ENABLE_PEOPLE_SEARCH_AGENT:
        pool.append(PeopleSearchAgent())
    return pool
