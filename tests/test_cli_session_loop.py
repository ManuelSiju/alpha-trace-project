from __future__ import annotations
import json

from click.testing import CliRunner

import cli.main as cli_main
from core.models.schema import Briefing, BriefingCategory


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


def test_plain_flag_produces_no_ansi_color(monkeypatch):
    monkeypatch.setattr(cli_main, "_run", _fake_run)
    monkeypatch.setattr(cli_main, "_ollama_status", lambda c: None)

    runner = CliRunner()
    result = runner.invoke(cli_main.cli, ["--plain", "--fast", "investigate", "--name", "Dana", "--no-chat"])

    assert result.exit_code == 0, result.output
    assert "\x1b[" not in result.output


def test_plain_flag_does_not_leak_into_later_non_plain_run(monkeypatch):
    """Regression: console must be rebuilt every invocation, not just when plain=True."""
    monkeypatch.setattr(cli_main, "_run", _fake_run)
    monkeypatch.setattr(cli_main, "_ollama_status", lambda c: None)

    runner = CliRunner()
    runner.invoke(cli_main.cli, ["--plain", "investigate", "--name", "Eve", "--no-chat"])
    assert cli_main.console.no_color is True

    runner.invoke(cli_main.cli, ["investigate", "--name", "Finn", "--no-chat"])
    assert cli_main.console.no_color is False


def test_detective_vocabulary_present_in_briefing_output(monkeypatch):
    monkeypatch.setattr(cli_main, "_run", _fake_run)
    monkeypatch.setattr(cli_main, "_ollama_status", lambda c: None)

    runner = CliRunner()
    result = runner.invoke(cli_main.cli, ["--fast", "investigate", "--name", "Grace", "--no-chat"])

    assert result.exit_code == 0, result.output
    for phrase in (
        "CASE SUMMARY", "KEY DEDUCTIONS", "TIMELINE OF EVENTS",
        "CONNECTIONS", "GAPS IN THE RECORD", "Case File No. 221-B-",
    ):
        assert phrase in result.output, phrase


def _sample_briefing() -> Briefing:
    return Briefing(
        target="Export Sample",
        overview="A short overview.",
        categories=[BriefingCategory(category="Web Presence", summary="1 finding.", confidence=60, sources=1, details=["a detail"])],
    )


def test_export_briefing_writes_markdown_by_default(tmp_path):
    b = _sample_briefing()
    out = cli_main._export_briefing(b, str(tmp_path / "case"))
    assert out.suffix == ".md"
    text = out.read_text()
    assert "Export Sample" in text
    assert "Web Presence" in text
    assert "a detail" in text


def test_export_briefing_writes_json_when_requested(tmp_path):
    b = _sample_briefing()
    out = cli_main._export_briefing(b, str(tmp_path / "case.json"))
    data = json.loads(out.read_text())
    assert data["target"] == "Export Sample"
    assert data["categories"][0]["category"] == "Web Presence"


def test_export_command_in_chat_writes_real_file(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_main, "_run", lambda target: _sample_briefing())
    monkeypatch.setattr(cli_main, "_ollama_status", lambda c: None)

    export_path = tmp_path / "out.md"
    runner = CliRunner()
    piped_input = f"x\nname\nIvy\n/export\n{export_path}\n/done\nq\n"
    result = runner.invoke(cli_main.cli, ["--fast", "interactive"], input=piped_input)

    assert result.exit_code == 0, result.output
    assert export_path.exists()
    assert "Export Sample" in export_path.read_text()
    assert "Exported to" in result.output  # path may wrap across lines at console width


def test_consulting_room_and_221b_prompt_appear_in_chat(monkeypatch):
    monkeypatch.setattr(cli_main, "_run", _fake_run)
    monkeypatch.setattr(cli_main, "_ollama_status", lambda c: None)
    monkeypatch.setattr(cli_main, "chat", lambda briefing, q, history: "an answer")

    runner = CliRunner()
    piped_input = "x\nname\nHal\n/done\nq\n"
    result = runner.invoke(cli_main.cli, ["--fast", "interactive"], input=piped_input)

    assert result.exit_code == 0, result.output
    assert "THE CONSULTING ROOM" in result.output
    assert "221B >" in result.output
