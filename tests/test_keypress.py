from __future__ import annotations
import io

import pytest

from core.utils.keypress import read_key, press_any_key, prompt_single_key


class _FakeStdin(io.StringIO):
    def isatty(self) -> bool:
        return False


def test_read_key_non_tty_returns_first_char(monkeypatch):
    monkeypatch.setattr("sys.stdin", _FakeStdin("n\n"))
    assert read_key() == "n"


def test_read_key_non_tty_eof_returns_empty(monkeypatch):
    monkeypatch.setattr("sys.stdin", _FakeStdin(""))
    assert read_key() == ""


def test_press_any_key_does_not_hang_on_piped_input(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", _FakeStdin("\n"))
    press_any_key("go>")
    assert "go>" in capsys.readouterr().out


def test_prompt_single_key_matches_choice(monkeypatch):
    monkeypatch.setattr("sys.stdin", _FakeStdin("n\n"))
    result = prompt_single_key("[N]/[Q]> ", {"n": "new case", "q": "close"})
    assert result == "n"


def test_prompt_single_key_skips_non_matching_lines(monkeypatch):
    monkeypatch.setattr("sys.stdin", _FakeStdin("x\ny\nq\n"))
    result = prompt_single_key("[N]/[Q]> ", {"n": "new case", "q": "close"})
    assert result == "q"


def test_prompt_single_key_raises_eof_on_exhausted_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", _FakeStdin(""))
    with pytest.raises(EOFError):
        prompt_single_key("[N]/[Q]> ", {"n": "new case", "q": "close"})
