from __future__ import annotations
import asyncio

from loguru import logger as loguru_logger

from core.agents.base_agent import BaseAgent
from core.models.schema import Target


class _BoomAgent(BaseAgent):
    name = "Boom"
    category = "Test"

    async def gather(self, target):
        raise RuntimeError("simulated failure")


def test_agent_failure_never_logs_a_raw_traceback():
    records: list[str] = []
    handler_id = loguru_logger.add(lambda m: records.append(m), level="DEBUG")
    try:
        findings = asyncio.run(_BoomAgent().run(Target(name="t")))
    finally:
        loguru_logger.remove(handler_id)

    assert findings == []
    joined = "\n".join(records)
    assert "Traceback" not in joined
    assert "simulated failure" in joined  # real cause is still visible, just no stack dump
