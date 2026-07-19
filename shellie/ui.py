"""Terminal formatting for agent activity (no LangChain debug dump)."""

import json
import sys

_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_PURPLE = "\033[35m"

_WORKING_LABEL = "shellie is working..."
_working_visible = False
_reply_active = False


def _use_color() -> bool:
    return sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if not _use_color():
        return text
    return f"{code}{text}{_RESET}"


def working_show() -> None:
    """Draw a blank separator line, then purple status (TTY only)."""
    global _working_visible
    if not _use_color() or _reply_active:
        return
    # Leading newline = empty line above the status so it doesn't sit on tool output.
    sys.stdout.write("\n" + _c(_PURPLE, _WORKING_LABEL))
    sys.stdout.flush()
    _working_visible = True


def working_clear() -> None:
    """Erase the status line and the blank separator above it (TTY only)."""
    global _working_visible
    if not _working_visible:
        return
    if _use_color():
        # Cursor sits on the status line (no trailing newline after show).
        sys.stdout.write("\r\033[2K")  # clear status line
        sys.stdout.write("\033[1A\r\033[2K")  # up to blank separator, clear it
        sys.stdout.write("\033[0J")  # drop any leftover empty line below
        sys.stdout.flush()
    _working_visible = False


def _activity_line(text: str) -> None:
    """Print a log line, keeping 'shellie is working...' as the last line."""
    working_clear()
    print(text)
    working_show()


def agent_calling_tool(name: str, args: dict) -> None:
    args_preview = json.dumps(args, ensure_ascii=False)
    if len(args_preview) > 120:
        args_preview = args_preview[:117] + "..."
    _activity_line(_c(_CYAN, f"→ {name}") + _c(_DIM, f"  {args_preview}"))


def shell_running(command: str) -> None:
    _activity_line(_c(_YELLOW, "  ▸ shell") + f"  $ {command}")


def shell_blocked(reason: str, command: str) -> None:
    _activity_line(
        _c(_RED, f"  ✗ blocked ({reason})") + _c(_DIM, f"  $ {command}")
    )


def shell_done(exit_code: int, line_count: int) -> None:
    if exit_code == 0:
        status = _c(_GREEN, f"  ✓ exit {exit_code}")
    else:
        status = _c(_RED, f"  ✗ exit {exit_code}")
    _activity_line(
        status
        + _c(_DIM, f"  ({line_count} line{'s' if line_count != 1 else ''} of output)")
    )


def confirm_sensitive(command: str) -> None:
    working_clear()
    print(_c(_YELLOW, "\n⚠ sensitive command — approval required"))
    print(f"  {command}")


def confirm_prompt() -> str:
    return _c(_BOLD, "Type 'yes' to run, anything else to cancel: ")


def agent_reply_start() -> None:
    global _reply_active
    working_clear()
    _reply_active = True
    print(_c(_DIM, "\n── reply " + "─" * 52))


def agent_reply_end() -> None:
    global _reply_active
    _reply_active = False
    print(_c(_DIM, "── reply end" + "─" * 52))


def format_tool_args(args: dict) -> str:
    if len(args) == 1:
        value = next(iter(args.values()))
        if isinstance(value, str) and "\n" not in value and len(value) < 80:
            return value
    return json.dumps(args, ensure_ascii=False)

def request_commands_approval(command: str) -> None:
    print(_c(_YELLOW, "\n⚠ sensitive command — approval required"))
    print(_c(_YELLOW, command))

def bold_text(text: str) -> str:
    return _c(_BOLD, text)

def commands_approved() -> None:
    print(_c(_GREEN, "  ✓ commands approved"))

def commands_rejected() -> None:
    print(_c(_RED, "  ✗ commands rejected"))