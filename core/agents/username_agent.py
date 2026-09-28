from __future__ import annotations
import asyncio
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import List

from loguru import logger

from core.agents.base_agent import BaseAgent
from core.models.schema import Target, Finding
from config.settings import settings


class UsernameAgent(BaseAgent):
    name = "UsernameAgent"
    category = "Username Footprint"

    async def gather(self, target: Target) -> List[Finding]:
        candidates = target.candidate_usernames()
        if not candidates:
            return []

        bin_path = shutil.which("sherlock")
        if not bin_path:
            sibling = Path(sys.executable).parent / "sherlock"
            if sibling.exists():
                bin_path = str(sibling)
        if not bin_path:
            logger.warning("sherlock not installed; skip username sweep")
            return []

        # Limit to first 3 candidates to keep runtime sane
        findings: List[Finding] = []
        for handle in candidates[:3]:
            findings.extend(await self._run_one(bin_path, handle))
        return findings

    async def _run_one(self, bin_path: str, handle: str) -> List[Finding]:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            try:
                proc = await asyncio.create_subprocess_exec(
                    bin_path,
                    handle,
                    "--print-found",
                    "--no-color",
                    "--output", str(out_dir / "result.txt"),
                    "--timeout", str(settings.SHERLOCK_PER_SITE_TIMEOUT),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, _ = await asyncio.wait_for(
                        proc.communicate(), timeout=settings.SHERLOCK_TIMEOUT + 30
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    logger.warning(f"sherlock timeout for {handle}")
                    return []
                text = stdout.decode("utf-8", errors="replace")
            except Exception as e:
                logger.error(f"sherlock error {handle}: {e}")
                return []

        hits = []
        for line in text.splitlines():
            m = re.match(r"^\[\+\]\s+(\S+):\s*(\S+)", line)
            if m:
                hits.append({"platform": m.group(1), "url": m.group(2)})

        if not hits:
            return [Finding(
                category=self.category,
                source=f"sherlock:{handle}",
                title=f"Handle '{handle}' not found on known platforms",
                content=f"Sherlock returned 0 positive hits for handle '{handle}'",
                confidence=35,
            )]

        return [Finding(
            category=self.category,
            source=f"sherlock:{handle}",
            title=f"Handle '{handle}' found on {len(hits)} platform(s)",
            content="; ".join(f"{h['platform']} -> {h['url']}" for h in hits[:20]),
            confidence=70,
            data={"handle": handle, "hits": hits},
        )]
