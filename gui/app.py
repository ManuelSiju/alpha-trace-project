from __future__ import annotations
import asyncio
import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.utils.logger import setup_logging
from core.models.schema import Briefing
from core.agents.orchestrator import Orchestrator, build_default_agents
from core.analyzers.profile_synthesizer import synthesize
from core.memory.session_store import SessionStore, sweep_stale_sessions
from core.llm.preflight import check_ollama

from gui.components.search_panel import render as render_search
from gui.components.briefing_panel import render as render_briefing
from gui.components.chat_panel import render as render_chat
from gui.components.graph_panel import render as render_graph
from gui.components.timeline_panel import render as render_timeline


setup_logging()

if "store" not in st.session_state:
    sweep_stale_sessions()
    st.session_state.store = SessionStore()
sessions = st.session_state.store

st.set_page_config(page_title="Alpha-Tracer", page_icon="🔎", layout="wide")

css_path = ROOT / "gui" / "styles" / "custom.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

logo_path = ROOT / "assets" / "alpha-trace.png"

# Main panel: logo beside readable title
hc1, hc2 = st.columns([1, 5])
with hc1:
    if logo_path.exists():
        st.image(str(logo_path), width=110)
    else:
        st.markdown("<div style='font-size:80px; line-height:1;'>🔎</div>", unsafe_allow_html=True)
with hc2:
    st.markdown(
        "<h1 style='margin-bottom:0; color:#c4ccff; letter-spacing:2px;'>ALPHA-TRACER</h1>"
        "<p style='color:#a8b5ff; margin-top:0;'>Contextual Intelligence Platform · Local LLM · OSS</p>",
        unsafe_allow_html=True,
    )

with st.sidebar:
    if logo_path.exists():
        st.image(str(logo_path), width=140)
    st.markdown("## Alpha-Tracer")
    st.caption("Local LLM · OSS · No paid API")
    st.markdown("---")
    _preflight = check_ollama()
    if _preflight.status == "ok":
        st.success(_preflight.message)
    else:
        _msg = _preflight.message + " Deterministic fallback will be used."
        if _preflight.fix:
            _msg += f" Fix: `{_preflight.fix}`"
        st.warning(_msg)
    st.markdown("---")
    if st.button("End session & wipe data", use_container_width=True):
        sid = st.session_state.get("session_id")
        if sid:
            res = sessions.purge_session(sid)
            st.success(f"Case closed. Session data destroyed. (cache files wiped: {res['cache_files_removed']})")
        st.session_state.briefing = None
        st.session_state.target = None
        st.session_state.session_id = None
        if "chat_history" in st.session_state:
            del st.session_state["chat_history"]
        st.rerun()


if "briefing" not in st.session_state:
    st.session_state.briefing = None
if "target" not in st.session_state:
    st.session_state.target = None
if "session_id" not in st.session_state:
    st.session_state.session_id = None


target = render_search()
if target is not None:
    sid = sessions.new_session(target)
    st.session_state.target = target
    st.session_state.session_id = sid
    with st.spinner("Gathering intelligence across agents..."):
        orch = Orchestrator(build_default_agents())
        t0 = time.monotonic()
        findings = asyncio.run(orch.run_all(target))
        elapsed = time.monotonic() - t0
    with st.spinner("Synthesizing briefing via local LLM..."):
        briefing = synthesize(target, findings, elapsed=elapsed)
    sessions.save_briefing(sid, briefing)
    st.session_state.briefing = briefing


if st.session_state.briefing is not None:
    b: Briefing = st.session_state.briefing
    tabs = st.tabs(["Briefing", "Q&A", "Graph", "Timeline", "Raw"])
    with tabs[0]:
        render_briefing(b)
    with tabs[1]:
        render_chat(b)
    with tabs[2]:
        render_graph(st.session_state.target, b)
    with tabs[3]:
        render_timeline(b)
    with tabs[4]:
        st.json([f.model_dump() for f in b.raw_findings])
else:
    st.info("Enter identifiers above and press Investigate.")
