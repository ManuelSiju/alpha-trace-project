from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List

from loguru import logger

from core.models.schema import Target, Finding


class BaseAgent(ABC):
    name: str = "BaseAgent"
    category: str = "Generic"

    def __init__(self) -> None:
        self.last_run: datetime | None = None
        self.last_error: str | None = None
        self.cache = None  # optional SessionStore-like cache; set by Orchestrator.run_all

    @abstractmethod
    async def gather(self, target: Target) -> List[Finding]:
        ...

    async def run(self, target: Target) -> List[Finding]:
        self.last_run = datetime.now(timezone.utc)
        try:
            findings = await self.gather(target)
            logger.info(f"[{self.name}] returned {len(findings)} finding(s)")
            return findings
        except Exception as e:
            self.last_error = str(e)
            # error(), not exception(): the console sink would otherwise print a
            # raw traceback to the user, which RL-1 explicitly forbids.
            logger.error(f"[{self.name}] failed: {e}")
            return []
