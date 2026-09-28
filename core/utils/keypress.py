from __future__ import annotations
import sys


def read_key() -> str:
    """Read a single keypress from stdin.

    Raw termios/tty on Linux/Mac, msvcrt on Windows. When stdin isn't a TTY
    (piped input, non-interactive contexts, most test runs) falls back to
    reading one line and returning its first character, so nothing hangs.
    Returns "" on EOF.
    """
    if not sys.stdin.isatty():
        line = sys.stdin.readline()
        return line[0] if line else ""

    if sys.platform == "win32":
        import msvcrt
        return msvcrt.getch().decode("utf-8", errors="replace")

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


def press_any_key(message: str = "Press any key to continue...") -> None:
    print(message, end="", flush=True)
    read_key()
    print()


def prompt_single_key(message: str, choices: dict[str, str]) -> str:
    """Print `message`, read keys until one matches a key in `choices`
    (case-insensitive), and return the matched lowercase key.

    `choices` maps single-character keys to their descriptions, e.g.
    {"n": "open a new case", "q": "close the case file"}. Raises
    KeyboardInterrupt on Ctrl-C and EOFError if stdin is exhausted, so
    callers can handle both the same way they handle an interactive Ctrl-C/Ctrl-D.
    """
    print(message, end="", flush=True)
    while True:
        ch = read_key()
        if not ch:
            print()
            raise EOFError("no input available")
        if ch == "\x03":
            print()
            raise KeyboardInterrupt
        ch = ch.lower()
        if ch in choices:
            print(ch)
            return ch
