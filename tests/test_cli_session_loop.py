from __future__ import annotations

from click.testing import CliRunner

import cli.main as cli_main
from core.models.schema import Briefing


def _fake_run(target):
    return Briefing.empty(target=target.primary_identifier())


def test_interactive_new_case_then_quit_purges_both(monkeypatch):
    """[N] opens a fresh case, [Q] closes it, and both purge — only Q announces it."""
    seen_targets: list[str] = []

    def fake_run(target):
        seen_targets.append(target.primary_identifier())
        return _fake_run(target)

    monkeypatch.setattr(cli_main, "_run", fake_run)
    monkeypatch.setattr(cli_main, "_ollama_status", lambda c: None)

    runner = CliRunner()
    # "x" = the splash keypress; then case 1 (name/Alice), /done, N, case 2 (name/Bob), /done, Q
    piped_input = "x\nname\nAlice\n/done\nn\nname\nBob\n/done\nq\n"
    result = runner.invoke(cli_main.cli, ["interactive"], input=piped_input)

    assert result.exit_code == 0, result.output
    assert seen_targets == ["Alice", "Bob"]
    assert "Case closed. Session data destroyed." in result.output
    # Only one closing message — the [N] branch must not print it.
    assert result.output.count("Case closed. Session data destroyed.") == 1
    assert cli_main.sessions.list_sessions() == []


def test_investigate_no_chat_purges_without_menu(monkeypatch):
    """--no-chat skips the Q&A loop and the [N]/[Q] menu, but still purges."""
    monkeypatch.setattr(cli_main, "_run", _fake_run)
    monkeypatch.setattr(cli_main, "_ollama_status", lambda c: None)

    runner = CliRunner()
    result = runner.invoke(cli_main.cli, ["investigate", "--name", "Carol", "--no-chat"])

    assert result.exit_code == 0, result.output
    assert "Open a new case" not in result.output
    assert cli_main.sessions.list_sessions() == []
