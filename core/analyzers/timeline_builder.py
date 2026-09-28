from __future__ import annotations
from typing import List, Dict, Any

from loguru import logger

from core.models.schema import Finding
from core.llm.ollama_client import get_llm


def build_timeline(findings: List[Finding]) -> List[Dict[str, Any]]:
    events = [
        {
            "source": f.source,
            "title": f.title or "",
            "content": f.content[:300],
            "timestamp": str(f.timestamp),
        }
        for f in findings
    ]
    try:
        return get_llm().build_timeline(events)
    except Exception as e:
        logger.error(f"timeline build failed: {e}")
        return []
