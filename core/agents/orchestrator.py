from __future__ import annotations
import asyncio
from typing import List, Dict, Type

from loguru import logger

from config.settings import settings
from core.models.schema import Target, Finding
from core.agents.base_agent import BaseAgent


class Orchestrator:
    """Fan-out runner. Each agent gets a timeout; errors isolated per-agent."""

    def __init__(self, agents: List[BaseAgent], timeout: int | None = None, cache=None):
        self.agents = agents
        self.timeout = timeout or settings.AGENT_TIMEOUT
        self.cache = cache

    async def run_all(self, target: Target, on_event=None) -> List[Finding]:
        """`on_event(agent_name, status, count=0)` fires for real state
        transitions only -- 'dispatched' when a run starts, then exactly one
        terminal call per agent: 'returned' (findings > 0), 'no_trail' (ran
        cleanly, 0 findings), or 'failed' (timeout, or an error the agent
        already caught internally). Never simulated or timer-driven -- every
        call corresponds to something that actually happened.
        """
        if not self.agents:
            return []

        for a in self.agents:
            a.cache = self.cache

        sem = asyncio.Semaphore(settings.MAX_CONCURRENT_REQUESTS)

        async def _bounded(agent: BaseAgent) -> List[Finding]:
            if on_event:
                on_event(agent.name, "dispatched")
            async with sem:
                if on_event:
                    on_event(agent.name, "reporting")
                try:
                    findings = await asyncio.wait_for(agent.run(target), timeout=self.timeout)
                except asyncio.TimeoutError:
                    logger.warning(f"[{agent.name}] timeout after {self.timeout}s")
                    if on_event:
                        on_event(agent.name, "failed")
                    return []
                if on_event:
                    if agent.last_error:
                        on_event(agent.name, "failed")
                    else:
                        on_event(agent.name, "returned" if findings else "no_trail", len(findings))
                return findings

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
    from core.agents.archive_agent import ArchiveAgent

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
    if settings.ENABLE_ARCHIVE_AGENT:
        pool.append(ArchiveAgent())
    return pool
