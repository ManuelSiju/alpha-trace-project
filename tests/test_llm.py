from __future__ import annotations
import json
import pytest

from core.llm.ollama_client import OllamaClient


def test_parse_json_direct():
    raw = '{"a": 1, "b": [1, 2]}'
    assert OllamaClient._parse_json(raw) == {"a": 1, "b": [1, 2]}


def test_parse_json_fenced():
    raw = "Sure thing!\n```json\n{\"x\": \"y\"}\n```\nhope that helps"
    assert OllamaClient._parse_json(raw) == {"x": "y"}


def test_parse_json_trailing_comma_repair():
    raw = '{"a": 1, "b": 2,}'
    parsed = OllamaClient._parse_json(raw)
    assert parsed == {"a": 1, "b": 2}


def test_parse_json_fallback_returns_raw():
    raw = "not json at all"
    parsed = OllamaClient._parse_json(raw)
    assert parsed == {"raw_response": "not json at all"}
