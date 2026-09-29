from __future__ import annotations
from collections import defaultdict
from typing import List, Dict

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
