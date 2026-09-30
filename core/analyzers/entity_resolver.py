from __future__ import annotations
import re
from collections import defaultdict
from typing import List, Dict, Any

from core.models.schema import Finding


def dedupe_findings(findings: List[Finding]) -> List[Finding]:
    """Collapse near-duplicate findings by (category, source, title)."""
    seen: Dict[str, Finding] = {}
    for f in findings:
        key = f"{f.category}|{f.source}|{f.title}"
        prev = seen.get(key)
        if not prev:
            seen[key] = f
            continue
        # keep highest-confidence
        if f.confidence > prev.confidence:
            seen[key] = f
    return list(seen.values())


def canonical_handles(findings: List[Finding]) -> Dict[str, List[str]]:
    """Group platform URLs by detected handle, so the same username/login
    showing up across independent sources (social probes, GitHub, sherlock
    hits) surfaces as one cross-platform identity instead of scattered,
    seemingly-unrelated findings."""
    by_handle: Dict[str, List[str]] = defaultdict(list)
    for f in findings:
        data = f.data or {}
        h = data.get("handle") or data.get("username") or data.get("login")
        if h and f.url:
            by_handle[h].append(f.url)
    return dict(by_handle)


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def correlate_identity(findings: List[Finding]) -> Dict[str, Any]:
    """Cross-reference the target's own signals to work out which accounts are
    corroborated (the same person confirmed by more than one independent
    source) vs. merely possible.

    The logic: a handle/email/real-name that shows up across multiple distinct
    agent sources is far more likely to be genuinely the target than one seen
    once. We tally, per identifier, how many *distinct* sources reference it,
    then tier: 2+ sources = corroborated, 1 = single-source lead. This is what
    turns a pile of 'possible' probes into 'these accounts are very likely the
    same person'.
    """
    handle_sources: Dict[str, set] = defaultdict(set)
    handle_urls: Dict[str, set] = defaultdict(set)
    email_sources: Dict[str, set] = defaultdict(set)
    name_sources: Dict[str, set] = defaultdict(set)

    for f in findings:
        src = f.source or "?"
        data = f.data or {}
        blob = f"{f.title or ''} {f.content or ''}"

        h = data.get("handle") or data.get("username") or data.get("login")
        if h:
            handle_sources[h].add(src)
            if f.url:
                handle_urls[h].add(f.url)

        # emails: explicit data field(s) + anything email-shaped in the text
        for e in (data.get("emails") or []):
            if e:
                email_sources[e.lower()].add(src)
        for e in _EMAIL_RE.findall(blob):
            email_sources[e.lower()].add(src)

        for key in ("full_name", "display_name", "name"):
            v = data.get(key)
            if v and isinstance(v, str) and " " in v.strip():
                name_sources[v.strip()].add(src)

    def _tier(n: int) -> str:
        return "corroborated" if n >= 2 else "single-source"

    corroborated_handles = {
        h: {"sources": sorted(s), "urls": sorted(handle_urls.get(h, [])), "tier": _tier(len(s))}
        for h, s in handle_sources.items()
    }
    corroborated_emails = {
        e: {"sources": sorted(s), "tier": _tier(len(s))} for e, s in email_sources.items()
    }
    corroborated_names = {
        n: {"sources": sorted(s), "tier": _tier(len(s))} for n, s in name_sources.items()
    }

    confirmed = sorted(h for h, v in corroborated_handles.items() if v["tier"] == "corroborated")
    return {
        "handles": corroborated_handles,
        "emails": corroborated_emails,
        "names": corroborated_names,
        "confirmed_handles": confirmed,
    }


def correlation_finding(findings: List[Finding]) -> Finding | None:
    """Render the correlation result as a single high-value briefing finding so
    the analyst sees, up front, which accounts are confirmed-vs-possible."""
    corr = correlate_identity(findings)
    confirmed = corr["confirmed_handles"]
    multi_emails = [e for e, v in corr["emails"].items() if v["tier"] == "corroborated"]
    multi_names = [n for n, v in corr["names"].items() if v["tier"] == "corroborated"]

    if not (confirmed or multi_emails or multi_names):
        return None

    bits = []
    if confirmed:
        bits.append("Handle(s) confirmed across multiple sources: " + ", ".join(confirmed))
    if multi_names:
        bits.append("Name(s) corroborated: " + ", ".join(multi_names))
    if multi_emails:
        bits.append("Email(s) corroborated: " + ", ".join(multi_emails))

    return Finding(
        category="Identity Correlation",
        source="correlator",
        title="Cross-source identity correlation",
        content="; ".join(bits),
        confidence=88 if confirmed else 70,
        data=corr,
    )
