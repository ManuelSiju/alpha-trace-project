from __future__ import annotations
import streamlit as st

from core.models.schema import Target, Briefing
from core.knowledge_graph.graph_builder import build
from core.knowledge_graph.visualizer import to_agraph


def render(target: Target, b: Briefing) -> None:
    st.markdown("### Knowledge Graph")
    try:
        from streamlit_agraph import agraph, Node, Edge, Config
    except ImportError:
        st.info("streamlit-agraph not installed — graph view disabled.")
        return

    g = build(target, b.raw_findings)
    nodes_dicts, edges_dicts = to_agraph(g)
    nodes = [Node(id=n["id"], label=n["label"], color=n["color"], size=n["size"]) for n in nodes_dicts]
    edges = [Edge(source=e["source"], target=e["target"]) for e in edges_dicts]
    config = Config(width=900, height=520, directed=True, physics=True, hierarchical=False)
    agraph(nodes=nodes, edges=edges, config=config)
