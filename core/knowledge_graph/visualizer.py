from __future__ import annotations
from typing import List, Tuple

from core.knowledge_graph.graph_builder import serialize


def to_agraph(g) -> Tuple[List[dict], List[dict]]:
    """Convert networkx graph to streamlit-agraph node/edge dicts."""
    payload = serialize(g)
    nodes = []
    for n in payload["nodes"]:
        node_type = n.get("type", "x")
        color = {
            "target": "#ff6b7a",
            "finding": "#a8b5ff",
            "url": "#7dd87d",
        }.get(node_type, "#cccccc")
        nodes.append({"id": n["id"], "label": (n.get("label") or n["id"])[:40], "color": color, "size": 20 if node_type == "target" else 12})
    edges = [{"source": e["source"], "target": e["target"]} for e in payload["edges"]]
    return nodes, edges
