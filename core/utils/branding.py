from __future__ import annotations
import time
from pathlib import Path

from rich.console import Console, Group
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.align import Align
from rich.table import Table
from rich import box


# Detective theme (UX-1): parchment/sepia + deep green, one gold accent.
# WARN/ERROR keep a distinct amber/red so real signals stay readable —
# everything decorative uses the theme palette instead.
PARCHMENT = "#d8c9a3"
SEPIA = "#a68a5b"
DEEP_GREEN = "#3a5a45"
ACCENT = "#c9a227"
MUTED = "#6b6b6b"

INDICATORS = {
    "ok": "[bold #7dd87d]✔[/]",
    "warn": "[bold #ffb86b]⚠[/]",
    "error": "[bold #ff6b7a]✘[/]",
    "info": f"[bold {ACCENT}]ℹ[/]",
    "processing": f"[bold {ACCENT}]◌[/]",
}

CATEGORY_ICONS = {
    "Email Intelligence": "✉",
    "Username Footprint": "@",
    "Web Presence": "◉",
    "Social Media": "♺",
    "GitHub": "⌥",
    "Domain Info": "⌬",
    "Public Records": "▤",
    "Breach Exposure": "⚠",
    "Phone Intelligence": "☏",
    "Image Metadata": "▣",
    "Archived Web": "⌛",
}

# Block-letter ALPHA-TRACER, easily readable
TITLE_LINES = [
    "█▀█ █   █▀█ █ █ █▀█   ▀█▀ █▀█ █▀█ █▀▀ █▀▀ █▀█",
    "█▀█ █▄▄ █▀▀ █▀█ █▀█    █  █▀▄ █▀█ █▄▄ ██▄ █▀▄",
]

LOGO_GLYPH = [
    "   ╭─────╮  ",
    "  ╱  α    ╲ ",
    "  ╲       ╱ ",
    "   ╰──╮──╯  ",
    "      ╲     ",
    "       ╲    ",
]


def _render_header() -> Panel:
    # Left: stylized magnifier+alpha logo glyph
    logo_text = Text("\n".join(LOGO_GLYPH), style=f"bold {PARCHMENT}")
    # Right: title + subtitle
    title = Text("\n".join(TITLE_LINES), style=f"bold {PARCHMENT}")
    subtitle = Text("Contextual Intelligence Platform · Local LLM · OSS", style=SEPIA)
    spacer = Text("")
    right = Group(spacer, title, spacer, subtitle)
    cols = Columns([logo_text, right], padding=(0, 4), expand=False)
    return Panel(cols, border_style=DEEP_GREEN, box=box.ROUNDED, padding=(0, 2))


def display_logo(console: Console | None = None, plain: bool = False) -> None:
    c = console or Console()
    if plain:
        c.print("ALPHA-TRACER")
        return
    c.print(_render_header())


def display_compact_logo(console: Console | None = None) -> None:
    c = console or Console()
    c.print("[bold #c4ccff]🔎 α-Tracer[/]  [#6b6b6b]·[/]  [#a8b5ff]Contextual Intelligence[/]")


def display_separator(ch: str = "─", color: str = "#2a2a2a", width: int = 78, console: Console | None = None) -> None:
    c = console or Console()
    c.print(f"[{color}]{ch * width}[/]")


def create_data_panel(title: str, data: dict, icon: str = "◈") -> Panel:
    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_column(style=SEPIA)
    t.add_column(style="#ffffff")
    for k, v in data.items():
        t.add_row(str(k), str(v))
    return Panel(t, title=f"{icon} {title}", border_style=DEEP_GREEN, box=box.ROUNDED)


def display_splash(console: Console | None = None, plain: bool = False) -> None:
    """Title card: 'ALPHA-TRACER: The Game Is Afoot', monochrome magnifier/alpha
    mark, parchment/sepia + deep-green palette. `plain` drops box-drawing and
    color entirely, for piped output or no-color terminals."""
    c = console or Console()
    if plain:
        c.print("ALPHA-TRACER: The Game Is Afoot")
        c.print("Contextual Intelligence Platform - Local LLM - OSS")
        return
    logo_text = Text("\n".join(LOGO_GLYPH), style=f"bold {PARCHMENT}")
    title = Text("ALPHA-TRACER", style=f"bold {PARCHMENT}")
    tagline = Text("The Game Is Afoot", style=f"italic {ACCENT}")
    subtitle = Text("Contextual Intelligence Platform · Local LLM · OSS", style=SEPIA)
    spacer = Text("")
    right = Group(spacer, title, tagline, spacer, subtitle)
    cols = Columns([logo_text, right], padding=(0, 4), expand=False)
    c.print(Panel(cols, border_style=DEEP_GREEN, box=box.DOUBLE, padding=(0, 2)))


def wax_seal_divider(console: Console | None = None, width: int = 78, plain: bool = False) -> None:
    c = console or Console()
    if plain:
        c.print("-" * width)
        return
    seal = " ❦ "
    side = "─" * ((width - len(seal)) // 2)
    c.print(f"[{DEEP_GREEN}]{side}[{ACCENT}]{seal}[/{ACCENT}]{side}[/{DEEP_GREEN}]")


def typewriter(text: str, console: Console | None = None, style: str = "", delay: float = 0.012, fast: bool = False) -> None:
    """Reveal `text` character by character. `fast=True` (or non-TTY output)
    prints instantly instead — never makes piped/redirected output wait."""
    c = console or Console()
    if fast or not c.is_terminal:
        c.print(text, style=style or None)
        return
    for ch in text:
        c.print(ch, style=style or None, end="")
        time.sleep(delay)
    c.print()


def case_number(session_id: str) -> str:
    """Cosmetic Baker-Street-style case number derived from the real session id."""
    tail = "".join(c for c in session_id if c.isalnum())[-4:].upper()
    return f"221-B-{tail}"
