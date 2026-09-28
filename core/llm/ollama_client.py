from __future__ import annotations
import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from core.llm.prompts import (
    SYNTH_SYSTEM,
    CHAT_SYSTEM,
    ENTITY_EXTRACT_SYSTEM,
    TIMELINE_SYSTEM,
    RELATIONSHIP_SYSTEM,
)


class OllamaUnavailable(RuntimeError):
    pass


class OllamaClient:
    """Local LLM client. Wraps Ollama HTTP API at OLLAMA_HOST."""

    def __init__(self, model: Optional[str] = None, host: Optional[str] = None):
        try:
            import ollama
        except ImportError as e:
            raise OllamaUnavailable(
                "ollama package not installed. pip install ollama"
            ) from e
        self._ollama = ollama
        self.host = host or settings.OLLAMA_HOST
        self.model = model or settings.OLLAMA_MODEL
        self.client = ollama.Client(host=self.host)

    def health_check(self) -> bool:
        try:
            self.client.list()
            return True
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False

    def ensure_model(self) -> None:
        try:
            models_resp = self.client.list()
            available = [m.get("name") or m.get("model") for m in models_resp.get("models", [])]
            if self.model not in available and not any(
                (n or "").startswith(self.model.split(":")[0]) for n in available
            ):
                logger.info(f"Pulling model {self.model} (first-run download)")
                self.client.pull(self.model)
                logger.success(f"Model {self.model} ready")
        except Exception as e:
            logger.error(f"Ollama model check failed: {e}")
            raise

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=8))
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        options: Dict[str, Any] = {
            "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
            "num_predict": max_tokens or settings.LLM_MAX_TOKENS,
        }
        kwargs: Dict[str, Any] = {"model": self.model, "messages": messages, "options": options}
        if json_mode:
            kwargs["format"] = "json"

        try:
            response = self.client.chat(**kwargs)
            return response["message"]["content"]
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            raise

    def analyze_briefing(self, target_label: str, findings_payload: List[Dict[str, Any]]) -> Dict[str, Any]:
        prompt = (
            f"Target: {target_label}\n\n"
            f"Raw findings (JSON):\n{json.dumps(findings_payload, indent=2, default=str)}\n\n"
            "Produce the briefing JSON now."
        )
        raw = self.generate(prompt, system_prompt=SYNTH_SYSTEM, json_mode=True, temperature=0.3)
        return self._parse_json(raw)

    def answer_question(
        self,
        question: str,
        briefing_context: Dict[str, Any],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        ctx = json.dumps(briefing_context, indent=2, default=str)
        history_str = ""
        if history:
            recent = history[-5:]
            history_str = "\n\nPrior turns:\n" + "\n".join(
                f"Q: {h.get('question','')}\nA: {h.get('answer','')}" for h in recent
            )
        prompt = f"Briefing context:\n{ctx}{history_str}\n\nUser question: {question}\n"
        return self.generate(prompt, system_prompt=CHAT_SYSTEM, temperature=0.5)

    def extract_entities(self, text: str) -> Dict[str, Any]:
        raw = self.generate(text, system_prompt=ENTITY_EXTRACT_SYSTEM, json_mode=True, temperature=0.2)
        return self._parse_json(raw)

    def build_timeline(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        raw = self.generate(
            json.dumps(events, default=str),
            system_prompt=TIMELINE_SYSTEM,
            json_mode=True,
            temperature=0.2,
        )
        parsed = self._parse_json(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "timeline" in parsed:
            return parsed["timeline"]
        return []

    def detect_relationships(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        raw = self.generate(
            json.dumps(entities, default=str),
            system_prompt=RELATIONSHIP_SYSTEM,
            json_mode=True,
            temperature=0.3,
        )
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(raw: str) -> Any:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # strip markdown fences
        m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        # grab first json object/array
        m = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
        if m:
            candidate = m.group(1)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                # try repair: trailing comma removal
                repaired = re.sub(r",(\s*[}\]])", r"\1", candidate)
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass
        logger.warning("Could not parse LLM JSON response; returning raw.")
        return {"raw_response": raw}


_client: Optional[OllamaClient] = None


def get_llm() -> OllamaClient:
    global _client
    if _client is None:
        _client = OllamaClient()
    return _client
