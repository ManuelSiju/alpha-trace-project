from __future__ import annotations
from typing import List, Dict, Any

import networkx as nx
from loguru import logger

from core.models.schema import Finding, Target


def build_graph(target: Target, findings: List[Finding]) -> nx.DiGraph:
    g = nx.DiGraph()
    root = target.primary_identifier()
    g.add_node(root, type="target", label=root)

    for f in findings:
        node_id = f"{f.source}:{f.title or f.content[:30]}"
        g.add_node(node_id, type="finding", label=(f.title or f.source), category=f.category, confidence=f.confidence)
        g.add_edge(root, node_id, weight=f.confidence / 100.0, source=f.source)
        # link to URL nodes
        if f.url:
            g.add_node(f.url, type="url", label=f.url)
            g.add_edge(node_id, f.url)

    return g


def graph_to_dicts(g: nx.DiGraph) -> Dict[str, Any]:
    nodes = [{"id": n, **(g.nodes[n] or {})} for n in g.nodes]
    edges = [{"source": u, "target": v, **(g.edges[u, v] or {})} for u, v in g.edges]
    return {"nodes": nodes, "edges": edges}
