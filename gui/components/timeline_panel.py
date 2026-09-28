from __future__ import annotations
import streamlit as st
import plotly.express as px
import pandas as pd

from core.models.schema import Briefing
from core.analyzers.timeline_builder import build_timeline


def render(b: Briefing) -> None:
    st.markdown("### Timeline")
    events = build_timeline(b.raw_findings)
    if not events:
        st.info("No timeline events extracted.")
        return
    df = pd.DataFrame(events)
    if "date" not in df.columns:
        st.write(df)
        return
    try:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date")
        fig = px.scatter(df, x="date", y=df.get("confidence", "High"), hover_data=df.columns,
                         title="Event timeline", color_discrete_sequence=["#a8b5ff"])
        fig.update_layout(plot_bgcolor="#0e0f14", paper_bgcolor="#0e0f14", font_color="#e6e6e6")
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.warning(f"timeline render failed: {e}")
        st.write(df)
