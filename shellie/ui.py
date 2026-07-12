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


def _use_color() -> bool:
    return sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if not _use_color():
        return text
    return f"{code}{text}{_RESET}"


def agent_calling_tool(name: str, args: dict) -> None:
    args_preview = json.dumps(args, ensure_ascii=False)
    if len(args_preview) > 120:
        args_preview = args_preview[:117] + "..."
    print(_c(_CYAN, f"\n→ {name}") + _c(_DIM, f"  {args_preview}"))


def shell_running(command: str) -> None:
    print(_c(_YELLOW, "  ▸ shell") + f"  $ {command}")


def shell_blocked(reason: str, command: str) -> None:
    print(_c(_RED, f"  ✗ blocked ({reason})") + _c(_DIM, f"  $ {command}"))


def shell_done(exit_code: int, line_count: int) -> None:
    if exit_code == 0:
        status = _c(_GREEN, f"  ✓ exit {exit_code}")
    else:
        status = _c(_RED, f"  ✗ exit {exit_code}")
    print(status + _c(_DIM, f"  ({line_count} line{'s' if line_count != 1 else ''} of output)"))


def confirm_sensitive(command: str) -> None:
    print(_c(_YELLOW, "\n⚠ sensitive command — approval required"))
    print(f"  {command}")


def confirm_prompt() -> str:
    return _c(_BOLD, "Type 'yes' to run, anything else to cancel: ")


def agent_reply_start() -> None:
    print(_c(_DIM, "\n── reply " + "─" * 52))


def format_tool_args(args: dict) -> str:
    if len(args) == 1:
        value = next(iter(args.values()))
        if isinstance(value, str) and "\n" not in value and len(value) < 80:
            return value
    return json.dumps(args, ensure_ascii=False)
