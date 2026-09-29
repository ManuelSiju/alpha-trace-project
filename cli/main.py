from __future__ import annotations
import asyncio
import sys
import time
from pathlib import Path

import click
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.utils.logger import setup_logging
from core.utils.branding import (
    display_logo, display_splash, wax_seal_divider,
    typewriter, case_number, create_data_panel,
    INDICATORS, CATEGORY_ICONS, ACCENT, DEEP_GREEN, SEPIA, MUTED, PARCHMENT,
)
from core.models.schema import Target, Briefing, Finding
from core.agents.orchestrator import Orchestrator, build_default_agents
from core.analyzers.profile_synthesizer import synthesize, chat, top_k_evidence
from core.analyzers.timeline_builder import build_timeline
from core.analyzers.entity_resolver import canonical_handles
from core.memory.session_store import SessionStore, sweep_stale_sessions
from core.utils.keypress import prompt_single_key, read_key
from core.llm.preflight import check_ollama


console = Console()
sessions = SessionStore()
sweep_stale_sessions()

_UI = {"plain": False, "fast": False}

IDENTIFIER_FIELDS = [
    ("email", "Email"),
    ("phone", "Phone (E.164 preferred)"),
    ("name", "Full name"),
    ("username", "Username / handle"),
    ("domain", "Domain"),
    ("company", "Company"),
    ("location", "Location hint"),
]
_SKIP_WORDS = {"nil", "none", "skip", "-", "n/a", "na"}


@click.group()
@click.option("--plain", is_flag=True, help="No color, no box-drawing — for piped output or no-color terminals.")
@click.option("--fast", is_flag=True, help="Disable the typewriter/reveal animation.")
def cli(plain: bool, fast: bool) -> None:
    """Alpha-Tracer — local-LLM OSINT platform."""
    global console
    _UI["plain"] = plain
    _UI["fast"] = fast
    # Always reconstruct: without this, a --plain invocation earlier in the same
    # process (e.g. in tests) would leak its no-color console into later runs.
    console = Console(no_color=True, highlight=False) if plain else Console()


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
        display_logo(console, plain=_UI["plain"])
        console.print()

        ids = dict(initial_ids) if first_case else {}
        if not ids:
            console.print(f"{INDICATORS['info']} What can you tell Watson about the subject? "
                          f"(enter what you have, leave blank or type 'nil' to skip any)")
            for key, label in IDENTIFIER_FIELDS:
                val = Prompt.ask(label, default="")
                if val and val.strip().lower() not in _SKIP_WORDS:
                    ids[key] = val.strip()
            if not ids:
                console.print(f"{INDICATORS['warn']} No identifiers provided — need at least one to investigate.")
                continue

        target = Target(**ids)
        session_id = sessions.new_session(target)
        cn = case_number(session_id)

        console.print(create_data_panel("Target Identifiers", {k: v for k, v in ids.items() if v}))
        console.print()
        _ollama_status(console)
        wax_seal_divider(console=console, plain=_UI["plain"])

        briefing = _run(target)
        sessions.save_briefing(session_id, briefing)

        _render(briefing)
        _render_full_text_dump(briefing)
        console.print(f"{INDICATORS['info']} Case File No. [{ACCENT}]{cn}[/]")

        if no_chat:
            sessions.purge_session(session_id, wipe_cache=True)
            return

        _chat_loop(briefing, session_id)

        try:
            choice = prompt_single_key(
                f"\n[bold {ACCENT}][N][/] Open a new case   [bold {ACCENT}][Q][/] Close the case file  > ",
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
    display_splash(console, plain=_UI["plain"])
    console.print()
    typewriter("Press any key to open a new case.", console, style=f"bold {ACCENT}", fast=_UI["fast"])
    read_key()
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
        line += f" Fix: [{ACCENT}]{res.fix}[/]"
    c.print(line)


AGENT_STATUS_LABELS = {
    "dispatched": ("Dispatched", ACCENT),
    "reporting": ("Reporting", ACCENT),
    "returned": ("Returned", "#7dd87d"),
    "no_trail": ("No Trail", MUTED),
    "failed": ("Failed", "#ff6b7a"),
}


def _agent_status_table(statuses: dict[str, tuple[str, int]]) -> Table:
    t = Table(title="Evidence Board", box=box.MINIMAL, show_header=True,
              header_style=f"bold {ACCENT}", title_style=f"bold {ACCENT}", border_style=DEEP_GREEN)
    t.add_column("Operative")
    t.add_column("Status")
    t.add_column("Evidence", justify="right")
    for name, (status, count) in statuses.items():
        label, color = AGENT_STATUS_LABELS.get(status, (status.title(), "#ffffff"))
        findings_cell = str(count) if status in ("returned", "no_trail") else "-"
        t.add_row(name, f"[{color}]{label}[/]", findings_cell)
    return t


def _run(target: Target) -> Briefing:
    orch = Orchestrator(build_default_agents(), cache=sessions)
    t0 = time.monotonic()

    statuses: dict[str, tuple[str, int]] = {a.name: ("dispatched", 0) for a in orch.agents}

    with Live(_agent_status_table(statuses), console=console, refresh_per_second=8, transient=True) as live:
        def on_event(name: str, status: str, count: int = 0) -> None:
            statuses[name] = (status, count)
            live.update(_agent_status_table(statuses))

        findings = asyncio.run(orch.run_all(target, on_event=on_event))

    elapsed = time.monotonic() - t0

    with Progress(SpinnerColumn(), TextColumn(f"[{ACCENT}]Watson is drafting the deductions...[/]"), transient=True, console=console) as p:
        tid = p.add_task("synth", start=True)
        briefing = synthesize(target, findings, elapsed=elapsed)
        p.update(tid, completed=True)
    return briefing


def _connections_summary(b: Briefing) -> str:
    sources = sorted({f.source for f in b.raw_findings})
    urls = sorted({f.url for f in b.raw_findings if f.url})
    lines = [f"{len(sources)} distinct source(s): " + ", ".join(sources[:10])]
    if urls:
        lines.append(f"{len(urls)} linked URL(s) connect the subject to external profiles and pages.")
    else:
        lines.append("No external URLs were linked to the subject.")

    handles = canonical_handles(b.raw_findings)
    for handle, handle_urls in handles.items():
        if len(handle_urls) > 1:
            # "probable", not "confirmed": these are HTTP-200 existence probes,
            # not verified account ownership -- matches the same honesty rule
            # the synthesizer applies to individual findings.
            lines.append(f"'{handle}' probable across {len(handle_urls)} platforms (unverified): " + ", ".join(handle_urls))
    return "\n".join(lines)


def _gaps_in_record(b: Briefing) -> list[Finding]:
    """Zero-confidence findings are status markers, not evidence — this is
    exactly where AG-1/AG-2's explicit 'no source configured' / 'search
    unavailable' findings surface, so gaps in coverage are visible, not silent."""
    return [f for f in b.raw_findings if f.confidence == 0]


def _render(b: Briefing) -> None:
    console.print()
    console.print(f"[bold {PARCHMENT}]CASE SUMMARY[/] · [{ACCENT}]{b.target}[/]")
    console.print()
    typewriter(b.overview or "(no overview)", console, style=SEPIA, fast=_UI["fast"])
    console.print()
    console.print(Panel.fit(
        f"[{MUTED}]data points:[/] {b.total_data_points}  "
        f"[{MUTED}]sources:[/] {b.total_sources}  "
        f"[{MUTED}]elapsed:[/] {b.elapsed_seconds:.1f}s\n"
        f"[{MUTED}]certainty:[/] "
        f"[#7dd87d]high {b.high_confidence_pct}%[/] · "
        f"[#ffb86b]med {b.medium_confidence_pct}%[/] · "
        f"[#ff6b7a]low {b.low_confidence_pct}%[/]",
        border_style=DEEP_GREEN,
        box=box.ROUNDED,
    ))
    console.print()
    console.print(f"[bold {PARCHMENT}]KEY DEDUCTIONS[/]")
    for c in b.categories:
        icon = CATEGORY_ICONS.get(c.category, "•")
        body = "\n".join(f"  • {d}" for d in c.details) if c.details else "  (no details)"
        evidence_note = f"  [{MUTED}]evidence:[/] {', '.join(c.evidence_ids)}" if c.evidence_ids else ""
        console.print(Panel(
            f"[{SEPIA}]{c.summary}[/]\n{body}\n\n"
            f"[{MUTED}]certainty:[/] {c.confidence}  [{MUTED}]sources:[/] {c.sources}{evidence_note}",
            title=f"{icon} {c.category}",
            border_style=DEEP_GREEN,
            box=box.ROUNDED,
        ))

    console.print()
    console.print(f"[bold {PARCHMENT}]TIMELINE OF EVENTS[/]")
    events = build_timeline(b.raw_findings) if b.raw_findings else []
    if events:
        for ev in events[:15]:
            console.print(f"  [{ACCENT}]{ev.get('date', '?')}[/]  {ev.get('event', '')}  "
                          f"[{MUTED}]({ev.get('source', '?')}, certainty: {ev.get('confidence', '?')})[/]")
    else:
        console.print(f"  [{MUTED}]No timeline available — requires the local LLM (Ollama offline or model unavailable).[/]")

    console.print()
    console.print(f"[bold {PARCHMENT}]CONNECTIONS[/]")
    console.print(f"  [{SEPIA}]{_connections_summary(b)}[/]")

    console.print()
    console.print(f"[bold {PARCHMENT}]GAPS IN THE RECORD[/]")
    gaps = _gaps_in_record(b)
    if gaps:
        for g in gaps:
            console.print(f"  [{MUTED}]•[/] {g.title}: {g.content}")
    else:
        console.print(f"  [{MUTED}]No known gaps — every operative reported a definite result.[/]")

    wax_seal_divider(console=console, plain=_UI["plain"])


END_COMMANDS = {"end", "end session", "/end", "/done", "quit", "exit", "q", ":q", "bye", "stop"}


def _show_evidence(briefing: Briefing, history: list[dict]) -> None:
    last_q = history[-1]["question"] if history else ""
    items = top_k_evidence(briefing, last_q)
    if not items:
        console.print(f"[{MUTED}]No evidence on file.[/]")
        return
    for f in items:
        url_line = f"  [{MUTED}]{f.url}[/]" if f.url else ""
        console.print(f"  [{ACCENT}]\\[{f.id}][/] [{SEPIA}]{f.category}·{f.source}[/] "
                      f"(certainty {f.confidence}) — {f.title or f.content[:80]}{url_line}")


def _show_timeline(briefing: Briefing) -> None:
    events = build_timeline(briefing.raw_findings) if briefing.raw_findings else []
    if not events:
        console.print(f"[{MUTED}]No timeline available — requires the local LLM.[/]")
        return
    for ev in events[:20]:
        console.print(f"  [{ACCENT}]{ev.get('date', '?')}[/]  {ev.get('event', '')}")


def _export_briefing(b: Briefing, path_str: str) -> Path:
    p = Path(path_str).expanduser()
    if p.suffix.lower() == ".json":
        p.write_text(b.model_dump_json(indent=2), encoding="utf-8")
    else:
        if not p.suffix:
            p = p.with_suffix(".md")
        lines = [f"# Case Summary: {b.target}", "", b.overview, ""]
        for c in b.categories:
            lines.append(f"## {c.category}")
            lines.append(c.summary)
            for d in c.details:
                lines.append(f"- {d}")
            lines.append("")
        p.write_text("\n".join(lines), encoding="utf-8")
    return p


def _handle_export(briefing: Briefing) -> None:
    try:
        path_str = Prompt.ask("Export path (.md or .json)")
    except (EOFError, KeyboardInterrupt):
        return
    if not path_str:
        return
    try:
        p = _export_briefing(briefing, path_str)
    except OSError as e:
        console.print(f"{INDICATORS['error']} Could not write export: {e}")
        return
    console.print(f"{INDICATORS['ok']} Exported to [{ACCENT}]{p}[/]")


def _chat_loop(briefing: Briefing, session_id: str) -> None:
    """Q&A loop. Ends when the user types an END_COMMAND, Ctrl-C, or Ctrl-D.

    Does not purge — the caller decides what to do next ([N]/[Q]), and both
    of those choices purge, per the session-store contract.
    """
    history: list[dict] = []
    console.print()
    console.print(Panel.fit(
        f"[bold {PARCHMENT}]THE CONSULTING ROOM[/]\n"
        f"Ask Watson anything about the subject.\n"
        f"Commands: [{ACCENT}]/evidence[/] [{ACCENT}]/timeline[/] [{ACCENT}]/export[/] [{ACCENT}]/done[/]",
        border_style=DEEP_GREEN,
        box=box.ROUNDED,
    ))
    while True:
        try:
            q = Prompt.ask(f"\n[bold {ACCENT}]221B >[/]")
        except (EOFError, KeyboardInterrupt):
            break
        q_norm = (q or "").strip().lower()
        if not q_norm or q_norm in END_COMMANDS:
            break
        if q_norm == "/evidence":
            _show_evidence(briefing, history)
            continue
        if q_norm == "/timeline":
            _show_timeline(briefing)
            continue
        if q_norm == "/export":
            _handle_export(briefing)
            continue
        ans = chat(briefing, q, history)
        console.print(Panel(ans, title="Watson", title_align="left", border_style=DEEP_GREEN, box=box.ROUNDED))
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
        f"[bold {PARCHMENT}]THE EVIDENCE LOCKER[/]\n"
        f"[{MUTED}]Every raw item of evidence gathered by every operative, id included.[/]",
        border_style=DEEP_GREEN,
        box=box.ROUNDED,
    ))
    for i, f in enumerate(b.raw_findings, 1):
        url_line = f"\n   [{MUTED}]url:[/] [{ACCENT}]{f.url}[/]" if f.url else ""
        console.print(
            f"\n[{MUTED}]{i:>2}.[/] [{ACCENT}]\\[{f.id}][/] [bold {PARCHMENT}]{f.category}[/] · [{SEPIA}]{f.source}[/]  "
            f"[{MUTED}](certainty {f.confidence})[/]"
        )
        console.print(f"   [bold]{f.title or '(no title)'}[/]")
        console.print(f"   [#e6e6e6]{f.content}[/]{url_line}")
    wax_seal_divider(console=console, plain=_UI["plain"])


if __name__ == "__main__":
    cli()
