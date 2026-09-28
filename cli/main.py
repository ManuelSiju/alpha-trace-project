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
from rich.table import Table
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
from core.memory.session_manager import SessionManager
from core.llm.ollama_client import get_llm, OllamaUnavailable
from config.settings import settings


console = Console()
sessions = SessionManager()


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
    console.clear()
    display_logo(console)
    console.print()

    ids = {k: v for k, v in {
        "email": email, "phone": phone, "name": name,
        "username": username, "domain": domain, "company": company,
        "location": location, "image_path": image_path,
    }.items() if v}

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

    if not no_chat:
        _chat_loop(briefing, session_id)


@cli.command()
def interactive() -> None:
    """Full guided session."""
    investigate.callback(email=None, phone=None, name=None, username=None,
                         domain=None, company=None, location=None,
                         image_path=None, no_chat=False)


@cli.command(name="list")
def list_sessions() -> None:
    """List saved sessions."""
    setup_logging()
    sids = sessions.list_sessions()
    if not sids:
        console.print("[#6b6b6b](no sessions)[/]")
        return
    t = Table(box=box.MINIMAL_DOUBLE_HEAD)
    t.add_column("Session", style="#a8b5ff")
    t.add_column("Target", style="#ffffff")
    for sid in sids:
        rec = sessions.load(sid)
        if rec:
            t.add_row(sid, rec.target.primary_identifier())
    console.print(t)


@cli.command()
@click.argument("session_id")
def show(session_id: str) -> None:
    """Show a saved briefing."""
    setup_logging()
    rec = sessions.load(session_id)
    if not rec or not rec.briefing:
        console.print(f"{INDICATORS['error']} Session not found or no briefing")
        return
    _render(rec.briefing)


def _ollama_status(c: Console) -> None:
    try:
        llm = get_llm()
        ok = llm.health_check()
        if ok:
            c.print(f"{INDICATORS['ok']} Ollama reachable at [#a8b5ff]{settings.OLLAMA_HOST}[/] · model [#a8b5ff]{settings.OLLAMA_MODEL}[/]")
            try:
                llm.ensure_model()
            except Exception as e:
                c.print(f"{INDICATORS['warn']} Could not verify model: {e}")
        else:
            c.print(f"{INDICATORS['warn']} Ollama not reachable — briefing will use deterministic fallback. Start daemon: [#a8b5ff]ollama serve &[/]")
    except OllamaUnavailable:
        c.print(f"{INDICATORS['warn']} `ollama` python package missing; deterministic fallback only.")
    except Exception as e:
        c.print(f"{INDICATORS['warn']} Ollama check error: {e}")


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


END_COMMANDS = {"end", "end session", "/end", "quit", "exit", "q", ":q", "bye", "stop"}


def _chat_loop(briefing: Briefing, session_id: str) -> None:
    history: list[dict] = []
    console.print()
    console.print(Panel.fit(
        "[bold #c4ccff]CHAT SESSION ACTIVE[/]\n"
        "Ask anything about the gathered intelligence.\n"
        f"Type [#a8b5ff]end[/] or [#a8b5ff]end session[/] to close — "
        "[#ff6b7a]all session data + cache will be wiped[/].",
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

    # End: purge
    result = sessions.purge_session(session_id, wipe_cache=True)
    console.print()
    console.print(Panel.fit(
        f"[bold #7dd87d]SESSION CLOSED[/]\n"
        f"Session file removed: [{'#7dd87d' if result['session_removed'] else '#ffb86b'}]{result['session_removed']}[/]\n"
        f"Cache rows wiped:     [#a8b5ff]{result['cache_rows_removed']}[/]\n"
        "[#6b6b6b]No gathered data retained on disk.[/]",
        border_style="#7dd87d",
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
