from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


def _launch_gui() -> None:
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(ROOT / "gui" / "app.py")],
        check=True,
    )


def _launch_cli(args: list[str]) -> None:
    from cli.main import cli
    cli(args, standalone_mode=True)


def _menu() -> None:
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.prompt import Prompt
        from rich import box
        from core.utils.branding import display_logo, INDICATORS

        console = Console()
        console.clear()
        display_logo(console)
        console.print()
        console.print(Panel.fit(
            "[bold #ffffff]Launch Alpha-Tracer[/]\n\n"
            "  [#a8b5ff]1[/] — CLI (rich terminal)\n"
            "  [#a8b5ff]2[/] — GUI (streamlit web)",
            border_style="#a8b5ff",
            box=box.ROUNDED,
        ))
        choice = Prompt.ask("Choice", choices=["1", "2"], default="1")
        if choice == "2":
            console.print(f"{INDICATORS['processing']} Launching GUI on localhost:8501...")
            _launch_gui()
        else:
            _launch_cli(["interactive"])
    except ImportError:
        print("Usage: python main.py [cli|gui] [...]")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        _menu()
    elif args[0] == "gui":
        _launch_gui()
    elif args[0] == "cli":
        _launch_cli(args[1:])
    else:
        _launch_cli(args)
