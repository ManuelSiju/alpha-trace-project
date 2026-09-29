from __future__ import annotations

from core.analyzers.entity_resolver import canonical_handles, dedupe_findings
from core.models.schema import Finding


def test_canonical_handles_groups_by_handle_key():
    findings = [
        Finding(category="Social Media", source="probe:instagram", title="x", content="",
                url="https://instagram.com/jcarter", data={"handle": "jcarter"}),
        Finding(category="Username Footprint", source="sherlock:jcarter", title="x", content="",
                url="https://github.com/jcarter", data={"handle": "jcarter"}),
    ]
    grouped = canonical_handles(findings)
    assert grouped["jcarter"] == ["https://instagram.com/jcarter", "https://github.com/jcarter"]


def test_canonical_handles_falls_back_to_username_then_login():
    findings = [
        Finding(category="Social Media", source="instagram", title="x", content="",
                url="https://instagram.com/jcarter", data={"username": "jcarter"}),
        Finding(category="GitHub", source="github:user", title="x", content="",
                url="https://github.com/jcarter", data={"login": "jcarter"}),
    ]
    grouped = canonical_handles(findings)
    assert sorted(grouped["jcarter"]) == sorted(["https://instagram.com/jcarter", "https://github.com/jcarter"])


def test_canonical_handles_ignores_findings_without_url_or_handle():
    findings = [
        Finding(category="Web Presence", source="web-search", title="x", content="", data={}),
        Finding(category="Social Media", source="probe:x", title="x", content="", url="https://x.com/a", data={}),
    ]
    assert canonical_handles(findings) == {}


def test_dedupe_findings_keeps_highest_confidence():
    findings = [
        Finding(category="Web Presence", source="s", title="t", content="a", confidence=40),
        Finding(category="Web Presence", source="s", title="t", content="b", confidence=90),
    ]
    result = dedupe_findings(findings)
    assert len(result) == 1
    assert result[0].confidence == 90
