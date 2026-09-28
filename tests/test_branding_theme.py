from __future__ import annotations
import io

from rich.console import Console

from core.utils.branding import display_splash, wax_seal_divider, typewriter, case_number


def _console_to(buf: io.StringIO, is_terminal: bool = False) -> Console:
    c = Console(file=buf, force_terminal=is_terminal, no_color=not is_terminal, width=80)
    return c


def test_display_splash_plain_has_no_box_drawing():
    buf = io.StringIO()
    display_splash(_console_to(buf), plain=True)
    out = buf.getvalue()
    assert "ALPHA-TRACER" in out
    assert "╭" not in out and "│" not in out


def test_display_splash_themed_mentions_tagline():
    buf = io.StringIO()
    display_splash(_console_to(buf, is_terminal=True), plain=False)
    out = buf.getvalue()
    assert "Game Is Afoot" in out


def test_wax_seal_divider_plain_is_plain_dashes():
    buf = io.StringIO()
    wax_seal_divider(_console_to(buf), width=20, plain=True)
    assert buf.getvalue().strip() == "-" * 20


def test_wax_seal_divider_themed_has_seal_glyph():
    buf = io.StringIO()
    wax_seal_divider(_console_to(buf, is_terminal=True), width=20, plain=False)
    assert "❦" in buf.getvalue()


def test_typewriter_fast_prints_immediately():
    buf = io.StringIO()
    typewriter("hello", _console_to(buf, is_terminal=True), fast=True)
    assert "hello" in buf.getvalue()


def test_typewriter_non_terminal_prints_immediately_without_delay():
    buf = io.StringIO()
    typewriter("hello", _console_to(buf, is_terminal=False), fast=False)
    assert "hello" in buf.getvalue()


def test_case_number_format():
    cn = case_number("ses_20260101_000000_abc123")
    assert cn.startswith("221-B-")
    assert cn == "221-B-C123"
