from __future__ import annotations
from pathlib import Path

from rich.console import Console, Group
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.align import Align
from rich.table import Table
from rich import box


INDICATORS = {
    "ok": "[bold #7dd87d]✔[/]",
    "warn": "[bold #ffb86b]⚠[/]",
    "error": "[bold #ff6b7a]✘[/]",
    "info": "[bold #a8b5ff]ℹ[/]",
    "processing": "[bold #a8b5ff]◌[/]",
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
    logo_text = Text("\n".join(LOGO_GLYPH), style="bold #c4ccff")
    # Right: title + subtitle
    title = Text("\n".join(TITLE_LINES), style="bold #c4ccff")
    subtitle = Text("Contextual Intelligence Platform · Local LLM · OSS", style="#a8b5ff")
    spacer = Text("")
    right = Group(spacer, title, spacer, subtitle)
    cols = Columns([logo_text, right], padding=(0, 4), expand=False)
    return Panel(cols, border_style="#a8b5ff", box=box.ROUNDED, padding=(0, 2))


def display_logo(console: Console | None = None) -> None:
    c = console or Console()
    c.print(_render_header())


def display_compact_logo(console: Console | None = None) -> None:
    c = console or Console()
    c.print("[bold #c4ccff]🔎 α-Tracer[/]  [#6b6b6b]·[/]  [#a8b5ff]Contextual Intelligence[/]")


def display_separator(ch: str = "─", color: str = "#2a2a2a", width: int = 78, console: Console | None = None) -> None:
    c = console or Console()
    c.print(f"[{color}]{ch * width}[/]")


def create_data_panel(title: str, data: dict, icon: str = "◈") -> Panel:
    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_column(style="#9aa3c4")
    t.add_column(style="#ffffff")
    for k, v in data.items():
        t.add_row(str(k), str(v))
    return Panel(t, title=f"{icon} {title}", border_style="#a8b5ff", box=box.ROUNDED)
