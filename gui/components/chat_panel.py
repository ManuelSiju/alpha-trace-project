from __future__ import annotations
import streamlit as st

from core.models.schema import Briefing
from core.analyzers.profile_synthesizer import chat


def render(b: Briefing, sessions=None, session_id: str | None = None, session_state_key: str = "chat_history") -> None:
    st.markdown("### Interactive Q&A")
    if session_state_key not in st.session_state:
        st.session_state[session_state_key] = []

    for turn in st.session_state[session_state_key]:
        with st.chat_message("user"):
            st.write(turn["question"])
        with st.chat_message("assistant"):
            st.write(turn["answer"])

    q = st.chat_input("Ask about this target")
    if q:
        with st.chat_message("user"):
            st.write(q)
        with st.spinner("Thinking..."):
            a = chat(b, q, st.session_state[session_state_key])
        with st.chat_message("assistant"):
            st.write(a)
        st.session_state[session_state_key].append({"question": q, "answer": a})
        if sessions is not None and session_id:
            sessions.append_chat(session_id, q, a)
