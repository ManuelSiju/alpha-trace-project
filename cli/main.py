from __future__ import annotations
import asyncio
import sys
import time
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Prompt, Confirm
from rich import box

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.utils.logger import setup_logging
from core.utils.branding import (
    display_logo, display_separator, create_data_panel,
    INDICATORS, CATEGORY_ICONS,
)
from core.models.schema import Target, Briefing
from core.agents.orchestrator import Orchestrator, build_default_agents
from core.analyzers.profile_synthesizer import synthesize, chat
from core.analyzers.entity_resolver import dedupe_findings
from core.memory.session_store import SessionStore, sweep_stale_sessions
from core.utils.keypress import press_any_key, prompt_single_key
from core.llm.preflight import check_ollama


console = Console()
sessions = SessionStore()
sweep_stale_sessions()


@click.group()
def cli() -> None:
    """Alpha-Tracer — local-LLM OSINT platform."""


@cli.command()
@click.option("--email", help="Email address")
@click.option("--phone", help="Phone number (E.164 preferred)")
@click.option("--name", help="Full name")
@click.option("--username", help="Handle / username")
@click.option("--domain", help="Domain name")
@click.option("--company", help="Company / org name")
@click.option("--location", help="Location hint")
@click.option("--image", "image_path", type=click.Path(exists=True, dir_okay=False), help="Image file for EXIF analysis")
@click.option("--no-chat", is_flag=True, help="Skip interactive Q&A loop after briefing")
def investigate(email, phone, name, username, domain, company, location, image_path, no_chat) -> None:
    """Run a new investigation."""
    setup_logging()

    initial_ids = {k: v for k, v in {
        "email": email, "phone": phone, "name": name,
        "username": username, "domain": domain, "company": company,
        "location": location, "image_path": image_path,
    }.items() if v}

    first_case = True
    while True:
        console.clear()
        display_logo(console)
        console.print()

        ids = dict(initial_ids) if first_case else {}
        if not ids:
            console.print(f"{INDICATORS['info']} Interactive identifier capture")
            kind = Prompt.ask("Identifier type", choices=["email", "phone", "name", "username", "domain", "company"], default="email")
            val = Prompt.ask(f"Enter {kind}")
            ids[kind] = val

        target = Target(**ids)
        session_id = sessions.new_session(target)

        console.print(create_data_panel("Target Identifiers", {k: v for k, v in ids.items() if v}))
        console.print()
        _ollama_status(console)
        display_separator(console=console)

        briefing = _run(target)
        sessions.save_briefing(session_id, briefing)

        _render(briefing)
        _render_full_text_dump(briefing)
        console.print(f"{INDICATORS['info']} Session: [#a8b5ff]{session_id}[/]")

        if no_chat:
            sessions.purge_session(session_id, wipe_cache=True)
            return

        _chat_loop(briefing, session_id)

        try:
            choice = prompt_single_key(
                "\n[bold #a8b5ff][N][/] Open a new case   [bold #a8b5ff][Q][/] Close the case file  > ",
                {"n": "open a new case", "q": "close the case file"},
            )
        except (EOFError, KeyboardInterrupt):
            choice = "q"

        result = sessions.purge_session(session_id, wipe_cache=True)
        if choice == "q":
            _print_case_closed(result)
            return

        first_case = False


@cli.command()
def interactive() -> None:
    """Full guided session."""
    console.clear()
    display_logo(console)
    console.print()
    press_any_key(f"{INDICATORS['info']} Press any key to open a new case...")
    investigate.callback(email=None, phone=None, name=None, username=None,
                         domain=None, company=None, location=None,
                         image_path=None, no_chat=False)


def _ollama_status(c: Console) -> None:
    res = check_ollama()
    if res.status == "ok":
        c.print(f"{INDICATORS['ok']} {res.message}")
        return
    line = f"{INDICATORS['warn']} {res.message} Deterministic fallback will be used."
    if res.fix:
        line += f" Fix: [#a8b5ff]{res.fix}[/]"
    c.print(line)


def _run(target: Target) -> Briefing:
    orch = Orchestrator(build_default_agents())
    t0 = time.monotonic()
    with Progress(SpinnerColumn(), TextColumn("[#a8b5ff]{task.description}[/]"), TimeElapsedColumn(), transient=True, console=console) as p:
        tid = p.add_task("Gathering intelligence...", start=True)
        findings = asyncio.run(orch.run_all(target))
        p.update(tid, completed=True)
    findings = dedupe_findings(findings)
    elapsed = time.monotonic() - t0

    with Progress(SpinnerColumn(), TextColumn("[#a8b5ff]Synthesizing briefing via local LLM...[/]"), transient=True, console=console) as p:
        tid = p.add_task("synth", start=True)
        briefing = synthesize(target, findings, elapsed=elapsed)
        p.update(tid, completed=True)
    return briefing


def _render(b: Briefing) -> None:
    console.print()
    console.print(Panel.fit(
        f"[bold #ffffff]INTELLIGENCE BRIEFING[/] · [#a8b5ff]{b.target}[/]\n\n"
        f"[#b0b0b0]{b.overview}[/]\n\n"
        f"[#6b6b6b]data points:[/] {b.total_data_points}  "
        f"[#6b6b6b]sources:[/] {b.total_sources}  "
        f"[#6b6b6b]elapsed:[/] {b.elapsed_seconds:.1f}s\n"
        f"[#6b6b6b]confidence:[/] "
        f"[#7dd87d]high {b.high_confidence_pct}%[/] · "
        f"[#ffb86b]med {b.medium_confidence_pct}%[/] · "
        f"[#ff6b7a]low {b.low_confidence_pct}%[/]",
        border_style="#a8b5ff",
        box=box.ROUNDED,
    ))
    console.print()
    for c in b.categories:
        icon = CATEGORY_ICONS.get(c.category, "•")
        body = "\n".join(f"  • {d}" for d in c.details) if c.details else "  (no details)"
        console.print(Panel(
            f"[#b0b0b0]{c.summary}[/]\n{body}\n\n"
            f"[#6b6b6b]confidence:[/] {c.confidence}  [#6b6b6b]sources:[/] {c.sources}",
            title=f"{icon} {c.category}",
            border_style="#3a3a3a",
            box=box.ROUNDED,
        ))
    display_separator(console=console)


END_COMMANDS = {"end", "end session", "/end", "/done", "quit", "exit", "q", ":q", "bye", "stop"}


def _chat_loop(briefing: Briefing, session_id: str) -> None:
    """Q&A loop. Ends when the user types an END_COMMAND, Ctrl-C, or Ctrl-D.

    Does not purge — the caller decides what to do next ([N]/[Q]), and both
    of those choices purge, per the session-store contract.
    """
    history: list[dict] = []
    console.print()
    console.print(Panel.fit(
        "[bold #c4ccff]CHAT SESSION ACTIVE[/]\n"
        "Ask anything about the gathered intelligence.\n"
        f"Type [#a8b5ff]/done[/] (or [#a8b5ff]end[/]) to close this case.",
        border_style="#a8b5ff",
        box=box.ROUNDED,
    ))
    while True:
        try:
            q = Prompt.ask("\n[#a8b5ff]ask[/]")
        except (EOFError, KeyboardInterrupt):
            break
        q_norm = (q or "").strip().lower()
        if not q_norm or q_norm in END_COMMANDS:
            break
        ans = chat(briefing, q, history)
        console.print(Panel(ans, border_style="#3a3a3a", box=box.ROUNDED))
        history.append({"question": q, "answer": ans})
        sessions.append_chat(session_id, q, ans)


def _print_case_closed(result: dict) -> None:
    if result["session_removed"]:
        console.print(Panel.fit(
            "[bold #7dd87d]Case closed. Session data destroyed.[/]\n"
            f"[#6b6b6b]cache files wiped: {result['cache_files_removed']}[/]",
            border_style="#7dd87d",
            box=box.ROUNDED,
        ))
    else:
        console.print(Panel.fit(
            "[bold #ffb86b]Session purge could not be verified — "
            "no in-memory record was found to remove.[/]",
            border_style="#ffb86b",
            box=box.ROUNDED,
        ))


def _render_full_text_dump(b: Briefing) -> None:
    console.print()
    console.print(Panel.fit(
        "[bold #c4ccff]COLLECTED DATA — FULL TEXT DUMP[/]\n"
        "[#6b6b6b]Every raw finding from every agent, presented as plain text.[/]",
        border_style="#a8b5ff",
        box=box.ROUNDED,
    ))
    for i, f in enumerate(b.raw_findings, 1):
        url_line = f"\n   [#6b6b6b]url:[/] [#a8b5ff]{f.url}[/]" if f.url else ""
        console.print(
            f"\n[#9aa3c4]{i:>2}.[/] [bold #c4ccff]{f.category}[/] · [#a8b5ff]{f.source}[/]  "
            f"[#6b6b6b](conf {f.confidence})[/]"
        )
        console.print(f"   [bold]{f.title or '(no title)'}[/]")
        console.print(f"   [#e6e6e6]{f.content}[/]{url_line}")
    display_separator(console=console)


if __name__ == "__main__":
    cli()
