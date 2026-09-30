from __future__ import annotations

from core.analyzers.entity_resolver import (
    canonical_handles, dedupe_findings, correlate_identity, correlation_finding,
)
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


def test_correlate_identity_tiers_by_source_count():
    findings = [
        # handle "jcarter" seen by 3 distinct sources -> corroborated
        Finding(category="GitHub", source="github:user", title="x", content="",
                url="https://github.com/jcarter", data={"handle": "jcarter"}),
        Finding(category="Social Media", source="probe:instagram", title="x", content="",
                url="https://instagram.com/jcarter", data={"handle": "jcarter"}),
        Finding(category="Username Footprint", source="sherlock:jcarter", title="x", content="",
                url="https://x.com/jcarter", data={"handle": "jcarter"}),
        # handle "jc99" seen once -> single-source
        Finding(category="Social Media", source="probe:reddit", title="x", content="",
                url="https://reddit.com/user/jc99", data={"handle": "jc99"}),
    ]
    corr = correlate_identity(findings)
    assert "jcarter" in corr["confirmed_handles"]
    assert "jc99" not in corr["confirmed_handles"]
    assert corr["handles"]["jcarter"]["tier"] == "corroborated"
    assert corr["handles"]["jc99"]["tier"] == "single-source"


def test_correlate_identity_emails_from_data_and_text():
    findings = [
        Finding(category="GitHub", source="github:commit-emails", title="x",
                content="", data={"emails": ["real@gmail.com"]}),
        Finding(category="Email Intelligence", source="parser", title="x",
                content="found real@gmail.com in metadata", data={}),
    ]
    corr = correlate_identity(findings)
    assert corr["emails"]["real@gmail.com"]["tier"] == "corroborated"


def test_correlation_finding_none_when_nothing_corroborated():
    findings = [
        Finding(category="Social Media", source="probe:instagram", title="x", content="",
                url="https://instagram.com/only", data={"handle": "only"}),
    ]
    assert correlation_finding(findings) is None


def test_correlation_finding_emitted_when_confirmed():
    findings = [
        Finding(category="GitHub", source="github:user", title="x", content="",
                url="https://github.com/jcarter", data={"handle": "jcarter"}),
        Finding(category="Social Media", source="probe:instagram", title="x", content="",
                url="https://instagram.com/jcarter", data={"handle": "jcarter"}),
    ]
    f = correlation_finding(findings)
    assert f is not None
    assert f.category == "Identity Correlation"
    assert "jcarter" in f.content
    assert "jcarter" in f.data["confirmed_handles"]
