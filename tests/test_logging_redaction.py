from __future__ import annotations
import asyncio

from core.utils.validators import redact, mask_email
from core.models.schema import Target
from core.agents.web_agent import WebAgent
from core.agents.github_agent import GitHubAgent


def test_redact_email():
    assert redact("jamiecarter2004@gmail.com") == mask_email("jamiecarter2004@gmail.com")
    assert "jamiecarter2004" not in redact("jamiecarter2004@gmail.com")


def test_redact_generic_identifier():
    out = redact("jamiecarter")
    assert out != "jamiecarter"
    assert out[0] == "j"
    assert out[-1] == "r"
    assert "jamiecarte" not in out


def test_redact_empty():
    assert redact(None) == "<empty>"
    assert redact("") == "<empty>"


def test_web_agent_logs_no_raw_identifier():
    def _fail_search(query: str) -> list[dict]:
        raise RuntimeError("boom")

    agent = WebAgent()
    agent._search = _fail_search
    target = Target(email="jamiecarter2004@gmail.com", name="Jamie Carter")

    import logging
    from loguru import logger as loguru_logger

    records: list[str] = []
    handler_id = loguru_logger.add(lambda m: records.append(m), level="DEBUG")
    try:
        asyncio.run(agent.gather(target))
    finally:
        loguru_logger.remove(handler_id)

    joined = "\n".join(records)
    assert "jamiecarter2004" not in joined
    assert "jamie carter" not in joined.lower()


def test_github_agent_logs_no_raw_identifier():
    from loguru import logger as loguru_logger

    async def _boom(*a, **k):
        raise RuntimeError("boom")

    agent = GitHubAgent()
    target = Target(email="jamiecarter2004@gmail.com")

    records: list[str] = []
    handler_id = loguru_logger.add(lambda m: records.append(m), level="DEBUG")
    try:
        import httpx

        class _BoomClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, *a, **k):
                raise RuntimeError("boom")

        import core.agents.github_agent as gh_mod
        orig = gh_mod.httpx.AsyncClient
        gh_mod.httpx.AsyncClient = lambda *a, **k: _BoomClient()
        try:
            asyncio.run(agent.gather(target))
        finally:
            gh_mod.httpx.AsyncClient = orig
    finally:
        loguru_logger.remove(handler_id)

    joined = "\n".join(records)
    assert "jamiecarter2004" not in joined
