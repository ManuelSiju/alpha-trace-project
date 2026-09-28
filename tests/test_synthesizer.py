from __future__ import annotations

import core.analyzers.profile_synthesizer as profile_synthesizer
from core.analyzers.profile_synthesizer import synthesize, chat, top_k_evidence
from core.llm.ollama_client import OllamaClient, OllamaUnavailable
from core.llm.prompts import CHAT_SYSTEM
from core.models.schema import Target, Finding, Briefing
from config.settings import settings


class _FakeLLM:
    """Captures the exact payload/context sent, so tests assert on what the
    synthesizer actually decided to send rather than on real LLM output."""

    def __init__(self):
        self.captured_payload = None
        self.captured_context = None

    def health_check(self) -> bool:
        return True

    def analyze_briefing(self, target_label, findings_payload):
        self.captured_payload = findings_payload
        cats = sorted({f["category"] for f in findings_payload})
        return {
            "target": target_label,
            "overview": "overview text",
            "categories": [
                {"category": c, "summary": f"summary for {c}", "confidence": 80, "sources": 1, "details": []}
                for c in cats
            ],
            "total_data_points": len(findings_payload),
            "total_sources": 1,
            "high_confidence_pct": 50,
            "medium_confidence_pct": 30,
            "low_confidence_pct": 20,
        }

    def answer_question(self, question, briefing_context, history=None):
        self.captured_context = briefing_context
        return "answer"


def test_num_ctx_always_set(monkeypatch):
    captured = {}
    llm = OllamaClient()

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return {"message": {"content": "ok"}}

    monkeypatch.setattr(llm.client, "chat", fake_chat)
    llm.generate("hello")
    assert captured["options"]["num_ctx"] == settings.OLLAMA_NUM_CTX


def test_rank_for_llm_caps_per_category_by_confidence():
    findings = [
        Finding(category="Cat", source="s", title=f"t{i}", content="x", confidence=i)
        for i in range(15)
    ]
    ranked = profile_synthesizer._rank_for_llm(findings)
    assert len(ranked) == settings.MAX_FINDINGS_PER_CATEGORY
    assert sorted(f.confidence for f in ranked) == list(range(15 - settings.MAX_FINDINGS_PER_CATEGORY, 15))


def test_deterministic_fallback_has_traceable_evidence_ids(monkeypatch):
    def raise_unavailable():
        raise OllamaUnavailable("no package")

    monkeypatch.setattr(profile_synthesizer, "get_llm", raise_unavailable)
    findings = [
        Finding(category="Cat A", source="s", title=f"t{i}", content="x", confidence=50 + i)
        for i in range(3)
    ]
    briefing = synthesize(Target(name="t"), findings)
    all_ids = {f.id for f in briefing.raw_findings}
    assert len(all_ids) == 3
    for cat in briefing.categories:
        assert set(cat.evidence_ids)
        assert set(cat.evidence_ids) <= all_ids


def test_llm_path_caps_payload_but_keeps_all_raw_findings(monkeypatch):
    fake = _FakeLLM()
    monkeypatch.setattr(profile_synthesizer, "get_llm", lambda: fake)
    findings = [
        Finding(category="Social", source="s", title=f"t{i}", content="x", confidence=i)
        for i in range(15)
    ]
    briefing = synthesize(Target(name="t"), findings)

    assert len(fake.captured_payload) == settings.MAX_FINDINGS_PER_CATEGORY
    sent_confidences = sorted(p["confidence"] for p in fake.captured_payload)
    assert sent_confidences == list(range(15 - settings.MAX_FINDINGS_PER_CATEGORY, 15))
    assert len(briefing.raw_findings) == 15  # nothing dropped from the record

    cat = briefing.categories[0]
    sent_ids = {p["id"] for p in fake.captured_payload}
    assert set(cat.evidence_ids) <= sent_ids
    assert set(cat.evidence_ids)


def test_10x_dataset_no_truncation_and_full_traceability(monkeypatch):
    """LA-4 acceptance: a 10x-normal-data fixture still yields a briefing with
    no truncation, and every category traces back to real evidence ids."""
    fake = _FakeLLM()
    monkeypatch.setattr(profile_synthesizer, "get_llm", lambda: fake)
    categories = [f"Cat{i}" for i in range(10)]
    findings = [
        Finding(category=cat, source="s", title=f"{cat}-{j}", content="x" * 50, confidence=j)
        for cat in categories
        for j in range(15)
    ]
    briefing = synthesize(Target(name="t"), findings)

    assert len(briefing.raw_findings) == 150
    all_ids = {f.id for f in briefing.raw_findings}
    assert len(all_ids) == 150  # every finding has a unique evidence id
    for c in briefing.categories:
        assert set(c.evidence_ids)
        assert set(c.evidence_ids) <= all_ids
    assert len(fake.captured_payload) == 10 * settings.MAX_FINDINGS_PER_CATEGORY


def test_chat_context_is_bounded_top_k(monkeypatch):
    fake = _FakeLLM()
    monkeypatch.setattr(profile_synthesizer, "get_llm", lambda: fake)
    findings = [
        Finding(category="Social", source="s", title=f"t{i}", content=f"content about topic{i}", confidence=50)
        for i in range(50)
    ]
    briefing = Briefing(target="t", raw_findings=findings)

    ans = chat(briefing, "tell me about topic5")

    assert ans == "answer"
    assert len(fake.captured_context["evidence"]) <= settings.CHAT_TOP_K_EVIDENCE
    assert any("topic5" in e["content"] for e in fake.captured_context["evidence"])


def test_top_k_evidence_falls_back_to_confidence_when_no_keyword_match():
    findings = [
        Finding(category="Social", source="s", title=f"t{i}", content="unrelated text", confidence=i)
        for i in range(20)
    ]
    briefing = Briefing(target="t", raw_findings=findings)
    top = top_k_evidence(briefing, "zzz_no_such_keyword_zzz", k=5)
    assert len(top) == 5
    assert sorted((f.confidence for f in top), reverse=True) == [f.confidence for f in top]


def test_chat_system_prompt_forbids_roleplay_and_requires_third_person():
    lowered = CHAT_SYSTEM.lower()
    assert "third person" in lowered
    assert "role-play" in lowered or "roleplay" in lowered
