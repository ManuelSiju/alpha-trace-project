from __future__ import annotations
import platform
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from core.llm.ollama_client import get_llm, OllamaUnavailable


@dataclass
class PreflightResult:
    status: str  # "ok" | "package_missing" | "server_down" | "model_pull_failed"
    message: str
    fix: Optional[str] = None


def _ollama_serve_fix() -> str:
    if platform.system() == "Windows":
        return "Open the Ollama app from the Start Menu, or run: ollama serve"
    return "ollama serve &"


def check_ollama() -> PreflightResult:
    """Single source of truth for CLI and GUI Ollama status: never leaks a raw
    exception to the user, always returns an actionable, OS-aware fix.
    """
    try:
        llm = get_llm()
    except OllamaUnavailable:
        return PreflightResult(
            status="package_missing",
            message="The `ollama` Python package is not installed.",
            fix="pip install ollama",
        )

    if not llm.health_check():
        return PreflightResult(
            status="server_down",
            message="Ollama server is not reachable.",
            fix=_ollama_serve_fix(),
        )

    try:
        llm.ensure_model()
    except Exception as e:
        logger.debug(f"ensure_model failed: {e}")
        return PreflightResult(
            status="model_pull_failed",
            message=f"Could not verify or pull model '{llm.model}'.",
            fix=f"ollama pull {llm.model}",
        )

    return PreflightResult(status="ok", message=f"Ollama reachable · model {llm.model}")
