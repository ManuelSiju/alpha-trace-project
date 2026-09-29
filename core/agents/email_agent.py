from __future__ import annotations
import asyncio
import hashlib
import shutil
import sys
import re
from pathlib import Path
from typing import List, Dict, Any

import httpx
from loguru import logger

from core.agents.base_agent import BaseAgent
from core.models.schema import Target, Finding
from core.utils.validators import is_email, email_local, email_domain
from core.utils.user_agent_rotator import default_headers
from config.settings import settings


PROVIDERS = {
    "gmail.com": "Google",
    "googlemail.com": "Google",
    "yahoo.com": "Yahoo",
    "outlook.com": "Microsoft",
    "hotmail.com": "Microsoft",
    "live.com": "Microsoft",
    "icloud.com": "Apple",
    "me.com": "Apple",
    "protonmail.com": "Proton",
    "proton.me": "Proton",
}

DISPOSABLE = {"tempmail.com", "guerrillamail.com", "10minutemail.com", "throwaway.email", "mailinator.com", "yopmail.com"}


class EmailAgent(BaseAgent):
    name = "EmailAgent"
    category = "Email Intelligence"

    async def gather(self, target: Target) -> List[Finding]:
        if not target.email or not is_email(target.email):
            return []
        email = target.email.lower().strip()
        findings: List[Finding] = []

        domain = email_domain(email) or ""
        local = email_local(email) or ""

        provider = PROVIDERS.get(domain, "Unknown / Custom")
        disposable = domain in DISPOSABLE
        pattern = self._email_pattern(local)

        findings.append(Finding(
            category=self.category,
            source="parser",
            title="Email metadata",
            content=f"Provider={provider}; domain={domain}; disposable={disposable}; pattern={pattern}",
            confidence=95,
            data={"provider": provider, "domain": domain, "disposable": disposable, "pattern": pattern},
        ))

        gravatar = await self._gravatar(email)
        if gravatar:
            findings.append(gravatar)

        holehe_hits = await self._run_holehe(email)
        findings.extend(holehe_hits)

        return findings

    @staticmethod
    def _email_pattern(local: str) -> str:
        if "." in local:
            return "firstname.lastname"
        if "_" in local:
            return "firstname_lastname"
        if re.search(r"\d{2,4}$", local):
            return "name+year"
        return "custom"

    @staticmethod
    def _venv_bin(name: str) -> str | None:
        """Find a sibling binary next to the running python (venv-friendly)."""
        candidate = Path(sys.executable).parent / name
        if candidate.exists() and candidate.is_file():
            return str(candidate)
        return None

    async def _gravatar(self, email: str) -> Finding | None:
        h = hashlib.md5(email.encode("utf-8")).hexdigest()
        avatar_url = f"https://www.gravatar.com/avatar/{h}?d=404"
        profile_url = f"https://www.gravatar.com/{h}.json"
        try:
            async with httpx.AsyncClient(timeout=10, headers=default_headers(), follow_redirects=True) as c:
                r = await c.head(avatar_url)
                if r.status_code != 200:
                    return None
                # Avatar exists -> pull the public profile JSON, which frequently
                # carries the real name, location, bio, and a list of the
                # person's own linked accounts (their own self-published data,
                # not scraped). This is the single richest free signal Gravatar
                # gives and was previously ignored.
                profile: Dict[str, Any] = {}
                try:
                    pr = await c.get(profile_url)
                    if pr.status_code == 200:
                        entries = (pr.json() or {}).get("entry") or []
                        if entries:
                            profile = entries[0]
                except Exception as e:
                    logger.debug(f"gravatar profile fetch failed: {e}")
        except Exception as e:
            logger.debug(f"gravatar check failed: {e}")
            return None

        display = profile.get("displayName") or profile.get("preferredUsername")
        name = (profile.get("name") or {})
        full_name = " ".join(v for v in [name.get("givenName"), name.get("familyName")] if v).strip()
        location = profile.get("currentLocation")
        about = ""
        if profile.get("aboutMe"):
            about = profile["aboutMe"][:200]
        accounts = [
            a.get("url") for a in (profile.get("accounts") or [])
            if isinstance(a, dict) and a.get("url")
        ]

        summary_bits = []
        if display:
            summary_bits.append(f"display={display}")
        if full_name:
            summary_bits.append(f"name={full_name}")
        if location:
            summary_bits.append(f"location={location}")
        if accounts:
            summary_bits.append(f"linked_accounts={len(accounts)}")
        content = "; ".join(summary_bits) if summary_bits else f"Gravatar avatar exists for {email}"

        return Finding(
            category=self.category,
            source="gravatar",
            title="Gravatar profile" + (" with public details" if summary_bits else " detected"),
            content=content + (f"; about={about}" if about else ""),
            url=f"https://www.gravatar.com/{h}",
            confidence=88 if profile else 85,
            data={
                "hash": h,
                "display_name": display,
                "full_name": full_name or None,
                "location": location,
                "about": about or None,
                "linked_accounts": accounts,
            },
        )

    async def _run_holehe(self, email: str) -> List[Finding]:
        bin_path = shutil.which("holehe") or self._venv_bin("holehe")
        if not bin_path:
            logger.warning("holehe not installed; skip site enumeration")
            return []

        try:
            proc = await asyncio.create_subprocess_exec(
                bin_path, email, "--only-used", "--no-color",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            except asyncio.TimeoutError:
                proc.kill()
                logger.warning("holehe timeout")
                return []
            text = stdout.decode("utf-8", errors="replace")
        except Exception as e:
            logger.error(f"holehe error: {e}")
            return []

        sites: List[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            # holehe output: "[+] site.com" for hit
            m = re.match(r"^\[\+\]\s+(\S+)", line)
            if m:
                sites.append(m.group(1))

        if not sites:
            return [Finding(
                category=self.category,
                source="holehe",
                title="No known site registrations",
                content=f"Holehe checked {len([l for l in text.splitlines() if l.strip()])} site signatures, no positive hit.",
                confidence=40,
            )]

        return [Finding(
            category=self.category,
            source="holehe",
            title=f"Email registered on {len(sites)} site(s)",
            content="Sites: " + ", ".join(sites[:25]),
            confidence=80,
            data={"sites": sites},
        )]
