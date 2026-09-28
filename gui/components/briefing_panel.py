from __future__ import annotations
import streamlit as st

from core.models.schema import Briefing
from core.utils.branding import CATEGORY_ICONS


def render(b: Briefing) -> None:
    st.markdown(f"### Briefing — `{b.target}`")
    st.markdown(f"_{b.overview}_")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Data points", b.total_data_points)
    m2.metric("Sources", b.total_sources)
    m3.metric("Elapsed", f"{b.elapsed_seconds:.1f}s")
    m4.metric("High conf %", b.high_confidence_pct)

    for c in b.categories:
        icon = CATEGORY_ICONS.get(c.category, "•")
        with st.expander(f"{icon}  {c.category}  ·  conf {c.confidence}  ·  src {c.sources}"):
            st.write(c.summary)
            for d in c.details:
                st.write(f"- {d}")

    with st.expander("📋  COLLECTED DATA — FULL TEXT DUMP", expanded=True):
        st.caption("Every raw finding from every agent, presented as plain text.")
        for i, f in enumerate(b.raw_findings, 1):
            st.markdown(
                f"**{i}. {f.category} · {f.source}** _(conf {f.confidence})_  \n"
                f"**{f.title or '(no title)'}**  \n"
                f"{f.content}"
                + (f"  \n[{f.url}]({f.url})" if f.url else "")
            )
