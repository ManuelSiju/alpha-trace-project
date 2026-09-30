from __future__ import annotations
import re
import time
from collections import Counter
from typing import List

from loguru import logger

from core.models.schema import Target, Finding, Briefing, BriefingCategory
from core.llm.ollama_client import get_llm, OllamaUnavailable
from core.analyzers.entity_resolver import dedupe_findings, correlation_finding
from config.settings import settings

# Exact 4-digit years — used to build the allowlist of years actually in findings.
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
# Broader date mentions to scrub from LLM prose: bare years AND decade phrases
# like "1990s", "mid-1990s", "early 2000s". Small models invent these to dodge
# the bare-year guard.
_DATE_RE = re.compile(
    r"\b(?:(?:early|mid|late)[\s-]+)?(?:19|20)\d0s\b|\b(?:19|20)\d{2}\b",
    re.IGNORECASE,
)
# English-month calendar dates ("July 13, 1995"). Findings store dates in ISO
# form (2025-07-11), never as month-name prose, so any such phrase in LLM output
# is fabricated regardless of which years happen to appear elsewhere.
_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
_MONTHDATE_RE = re.compile(
    rf"\b(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+(?:19|20)\d{{2}}\b"
    rf"|\b(?:{_MONTHS})\.?\s+(?:19|20)\d{{2}}\b",
    re.IGNORECASE,
)


def _finding_years(f: Finding) -> set[str]:
    return set(_YEAR_RE.findall(f"{f.content or ''} {f.title or ''} {f.url or ''}"))


def _sourced_years(findings: List[Finding]) -> set[str]:
    """Years that actually appear in raw findings (content/title/url)."""
    out: set[str] = set()
    for f in findings:
        out |= _finding_years(f)
    return out


def _years_by_category(findings: List[Finding]) -> dict[str, set[str]]:
    """Years appearing in each category's own findings. Used to bind a year to
    the evidence it came from so an LLM can't borrow a year from one category
    (e.g. a web snippet) to fabricate a fact in another (e.g. email creation)."""
    out: dict[str, set[str]] = {}
    for f in findings:
        out.setdefault(f.category, set()).update(_finding_years(f))
    return out


def _match_category(cat_name: str, by_cat: dict, fallback):
    """Fuzzy category-name match: exact, or substring either direction. Small
    models paraphrase category names, so an exact-only match would silently
    drop years/evidence-ids for anything it renamed."""
    cn = (cat_name or "").strip().lower()
    if not cn:
        return fallback
    for k, v in by_cat.items():
        kl = k.lower()
        if cn == kl or cn in kl or kl in cn:
            return v
    return fallback


def _allowed_years(cat_name: str, years_by_cat: dict[str, set[str]], fallback: set[str]) -> set[str]:
    return _match_category(cat_name, years_by_cat, fallback)


def _rank_for_llm(findings: List[Finding]) -> List[Finding]:
    """Deterministic reduction before the LLM ever sees anything: cap each
    category at MAX_FINDINGS_PER_CATEGORY, keeping the highest-confidence
    items. Briefing.raw_findings still retains every finding — this only
    bounds what goes into the prompt/context window."""
    by_cat: dict[str, list[Finding]] = {}
    for f in findings:
        by_cat.setdefault(f.category, []).append(f)
    ranked: List[Finding] = []
    for items in by_cat.values():
        items.sort(key=lambda f: f.confidence, reverse=True)
        ranked.extend(items[: settings.MAX_FINDINGS_PER_CATEGORY])
    return ranked


def _scrub_years(text: str, sourced_years: set[str]) -> str:
    """Replace any date mention in LLM text not backed by the raw findings.
    Bare years are kept only if that exact year appears in the findings; decade
    phrases ("mid-1990s") are always scrubbed since findings carry exact years.
    Small local models inject world-knowledge dates (e.g. gmail.com 'registered
    in 1995' / 'early 1990s') that aren't in the data."""
    if not text:
        return text

    # English-month calendar dates are never in our findings -> always scrub.
    text = _MONTHDATE_RE.sub("[unverified]", text)

    def repl(m: re.Match) -> str:
        token = m.group(0)
        # Keep only an exact bare year that is actually in the findings.
        if token in sourced_years:
            return token
        return "[unverified]"

    return _DATE_RE.sub(repl, text)


def _confidence_buckets(findings: List[Finding]) -> tuple[int, int, int]:
    high = sum(1 for f in findings if f.confidence >= 75)
    medium = sum(1 for f in findings if 45 <= f.confidence < 75)
    low = sum(1 for f in findings if f.confidence < 45)
    total = max(1, len(findings))
    return (
        round(100 * high / total),
        round(100 * medium / total),
        round(100 * low / total),
    )


def _deterministic_categories(findings: List[Finding]) -> list[BriefingCategory]:
    """Group findings by category with simple aggregation (no LLM)."""
    by_cat: dict[str, list[Finding]] = {}
    for f in findings:
        by_cat.setdefault(f.category, []).append(f)

    cats: list[BriefingCategory] = []
    for cat, items in by_cat.items():
        avg_conf = round(sum(i.confidence for i in items) / len(items))
        cats.append(BriefingCategory(
            category=cat,
            summary=f"{len(items)} finding(s) aggregated by source.",
            confidence=avg_conf,
            sources=len({i.source for i in items}),
            details=[i.content[:160] for i in items[:5]],
            evidence_ids=[i.id for i in items],
        ))
    return cats


def _coerce_categories(
    cats_raw,
    years_by_cat: dict[str, set[str]],
    fallback_years: set[str],
    ids_by_cat: dict[str, list[str]],
) -> list[BriefingCategory]:
    """Tolerantly build BriefingCategory list from LLM output.

    Small models sometimes emit category items as bare strings or with
    missing/odd-typed fields. Skip what we can't use instead of dropping all.
    Years not present in that category's own findings are scrubbed.
    """
    if not isinstance(cats_raw, list):
        return []
    out: list[BriefingCategory] = []
    for c in cats_raw:
        if not isinstance(c, dict):
            logger.debug(f"skipping non-dict category item: {c!r}")
            continue
        try:
            name = str(c.get("category", "")).strip() or "Uncategorized"
            allowed = _allowed_years(name, years_by_cat, fallback_years)
            details = c.get("details", [])
            if isinstance(details, str):
                details = [details]
            elif not isinstance(details, list):
                details = []
            out.append(BriefingCategory(
                category=name,
                summary=_scrub_years(str(c.get("summary", "")).strip(), allowed),
                confidence=int(c.get("confidence", 0) or 0),
                sources=int(c.get("sources", 0) or 0),
                details=[_scrub_years(str(d), allowed) for d in details],
                evidence_ids=_match_category(name, ids_by_cat, []),
            ))
        except Exception as e:
            logger.debug(f"skipping bad category item {c!r}: {e}")
            continue
    return out


def _fallback_briefing(target: Target, findings: List[Finding], elapsed: float) -> Briefing:
    """Used when LLM unavailable: deterministic aggregation only."""
    cats = _deterministic_categories(findings)

    h, m, l = _confidence_buckets(findings)
    return Briefing(
        target=target.primary_identifier(),
        overview=f"Deterministic briefing (LLM offline). {len(findings)} findings across {len(cats)} categories.",
        categories=cats,
        total_data_points=len(findings),
        total_sources=len({f.source for f in findings}),
        high_confidence_pct=h,
        medium_confidence_pct=m,
        low_confidence_pct=l,
        elapsed_seconds=elapsed,
        raw_findings=findings,
    )


def synthesize(target: Target, findings: List[Finding], elapsed: float = 0.0) -> Briefing:
    findings = dedupe_findings(findings)
    if not findings:
        return Briefing.empty(target.primary_identifier())

    # Cross-source correlation runs before synthesis so the LLM sees which
    # accounts/emails/names are corroborated (same person, multiple independent
    # sources) vs. single-source leads -- this is what lets it state, with
    # justified confidence, which accounts are actually the target's.
    corr = correlation_finding(findings)
    if corr:
        findings = [corr] + findings

    t0 = time.monotonic()
    llm_findings = _rank_for_llm(findings)
    payload = [
        {
            "id": f.id,
            "category": f.category,
            "source": f.source,
            "title": f.title,
            "content": f.content[:500],
            "url": f.url,
            "confidence": f.confidence,
        }
        for f in llm_findings
    ]
    ids_by_category: dict[str, list[str]] = {}
    for f in llm_findings:
        ids_by_category.setdefault(f.category, []).append(f.id)

    try:
        llm = get_llm()
        if not llm.health_check():
            logger.warning("Ollama not reachable; using deterministic fallback briefing")
            return _fallback_briefing(target, findings, elapsed)
        result = llm.analyze_briefing(target.primary_identifier(), payload)
    except OllamaUnavailable:
        logger.warning("Ollama package missing; deterministic fallback")
        return _fallback_briefing(target, findings, elapsed)
    except Exception as e:
        logger.error(f"LLM synthesize failed: {e}; using deterministic fallback")
        return _fallback_briefing(target, findings, elapsed)

    # Coerce to Briefing (tolerant: skip bad items, never drop all)
    sourced_years = _sourced_years(findings)
    years_by_cat = _years_by_category(findings)
    cats_raw = result.get("categories", []) if isinstance(result, dict) else []
    cats = _coerce_categories(cats_raw, years_by_cat, sourced_years, ids_by_category)
    if not cats and findings:
        logger.warning("LLM returned no usable categories; using deterministic categories")
        cats = _deterministic_categories(findings)

    # Overview spans all categories, so allow any year present anywhere in findings.
    overview = result.get("overview", "") if isinstance(result, dict) else ""
    overview = _scrub_years(overview, sourced_years)

    h, m, l = _confidence_buckets(findings)
    briefing = Briefing(
        target=result.get("target", target.primary_identifier()) if isinstance(result, dict) else target.primary_identifier(),
        overview=overview,
        categories=cats,
        total_data_points=int(result.get("total_data_points", len(findings))) if isinstance(result, dict) else len(findings),
        total_sources=int(result.get("total_sources", len({f.source for f in findings}))) if isinstance(result, dict) else len({f.source for f in findings}),
        high_confidence_pct=int(result.get("high_confidence_pct", h)) if isinstance(result, dict) else h,
        medium_confidence_pct=int(result.get("medium_confidence_pct", m)) if isinstance(result, dict) else m,
        low_confidence_pct=int(result.get("low_confidence_pct", l)) if isinstance(result, dict) else l,
        elapsed_seconds=elapsed or (time.monotonic() - t0),
        raw_findings=findings,
    )
    return briefing


def _score_finding(finding: Finding, terms: set[str]) -> int:
    haystack = f"{finding.category} {finding.source} {finding.title or ''} {finding.content}".lower()
    return sum(1 for t in terms if t in haystack)


def top_k_evidence(briefing: Briefing, question: str, k: int | None = None) -> List[Finding]:
    """Retrieve the k findings most relevant to `question` by keyword overlap,
    breaking ties by confidence. Keeps chat's per-turn context bounded instead
    of resending every raw finding regardless of briefing size."""
    k = k or settings.CHAT_TOP_K_EVIDENCE
    terms = set(re.findall(r"[a-z0-9]{3,}", question.lower()))
    scored = [(_score_finding(f, terms) if terms else 0, f.confidence, f) for f in briefing.raw_findings]
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    if terms and any(score > 0 for score, _, _ in scored):
        return [f for score, _, f in scored if score > 0][:k]
    return [f for _, _, f in scored[:k]]


def chat(briefing: Briefing, question: str, history: list[dict] | None = None) -> str:
    try:
        llm = get_llm()
        evidence = top_k_evidence(briefing, question)
        context = {
            "target": briefing.target,
            "overview": briefing.overview,
            "categories": [
                {"category": c.category, "summary": c.summary, "confidence": c.confidence}
                for c in briefing.categories
            ],
            "evidence": [
                {
                    "id": f.id,
                    "category": f.category,
                    "source": f.source,
                    "title": f.title,
                    "content": f.content[:400],
                    "url": f.url,
                    "confidence": f.confidence,
                }
                for f in evidence
            ],
        }
        return llm.answer_question(question, context, history)
    except Exception as e:
        logger.error(f"chat failed: {e}")
        return f"(LLM unavailable: {e})"
