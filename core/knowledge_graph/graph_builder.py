from __future__ import annotations
import networkx as nx
from typing import List

from core.models.schema import Target, Finding
from core.analyzers.relationship_mapper import build_graph, graph_to_dicts


def build(target: Target, findings: List[Finding]) -> nx.DiGraph:
    return build_graph(target, findings)


def serialize(g: nx.DiGraph) -> dict:
    return graph_to_dicts(g)
