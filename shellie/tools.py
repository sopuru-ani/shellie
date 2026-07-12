import platform
import re
from datetime import datetime
from pathlib import Path

from langchain_community.tools import DuckDuckGoSearchRun, WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_core.tools import tool

from shellie.cognee_memory import (
    recall_device as _recall_device,
    recall_project as _recall_project,
    remember_device as _remember_device,
    remember_project as _remember_project,
)
from shellie.shell import get_shell
from shellie.ui import confirm_prompt, confirm_sensitive, shell_blocked, shell_done, shell_running

INTERACTIVE_COMMAND_PATTERNS = [
    re.compile(r"\bgh\s+auth\s+(login|refresh)\b", re.I),
    re.compile(r"\b(vim?|nano|emacs|nvim)\b", re.I),
    re.compile(r"\b(less|more)\b", re.I),
    re.compile(r"\bman\b", re.I),
    re.compile(r"\b(top|htop|btop)\b", re.I),
    re.compile(r"\bwatch\b", re.I),
    re.compile(r"\bpasswd\b", re.I),
    re.compile(r"\bsu\b", re.I),
    re.compile(r"\b(ipython|bpython)\b", re.I),
    re.compile(r"\bmysql\b", re.I),
    re.compile(r"\bpsql\b", re.I),
    re.compile(r"\bgit\s+commit\b(?![^\n]*\s-m\b)", re.I),
    re.compile(r"\bgit\s+rebase\b(?![^\n]*--continue)", re.I),
    re.compile(r"\bgit\s+add\s+(-p|--patch)\b", re.I),
    re.compile(r"\b(ftp|telnet)\b", re.I),
    re.compile(r"^python3?\s*$", re.I),
    re.compile(r"^node\s*$", re.I),
]

SSH_NONINTERACTIVE = re.compile(
    r"\bssh\b.*(-T\b|-N\b|-f\b|-o\s+BatchMode=yes)",
    re.I,
)

search_tool = DuckDuckGoSearchRun()

api_wrapper = WikipediaAPIWrapper(top_k_results=1, doc_content_chars_max=100)
wikipedia_tool = WikipediaQueryRun(api_wrapper=api_wrapper)

SENSITIVE_COMMAND_PATTERNS = [
    re.compile(r"\bgit\s+push\b", re.I),
    re.compile(r"\bgit\s+pull\b", re.I),
    re.compile(r"\bgit\s+fetch\b", re.I),
    re.compile(r"\brm\b", re.I),
    re.compile(r"\bmv\b", re.I),
    re.compile(r"\bsudo\b", re.I),
    re.compile(r"\b(chmod|chown)\b", re.I),
    re.compile(r"\b(pip|pip3|npm|apt|dnf|yum|brew)\s+(install|uninstall|remove)\b", re.I),
    re.compile(r"\bgit\s+config\b", re.I),
    re.compile(r"(curl|wget).*\|\s*(ba)?sh", re.I),
]


def _is_sensitive_command(command: str) -> bool:
    return any(pattern.search(command) for pattern in SENSITIVE_COMMAND_PATTERNS)


def _is_interactive_command(command: str) -> bool:
    stripped = command.strip()
    if SSH_NONINTERACTIVE.search(stripped):
        return False
    if re.search(r"\bssh\b", stripped, re.I):
        return True
    return any(pattern.search(stripped) for pattern in INTERACTIVE_COMMAND_PATTERNS)


def _interactive_block_message(command: str) -> str:
    return (
        "exit_code: blocked\n\n"
        "Command not run: interactive command (needs a real terminal with keyboard input).\n"
        "Run it yourself in Konsole or another system terminal, then tell the assistant "
        "when you're done so it can continue with non-interactive commands.\n\n"
        "Examples: gh auth login, ssh, vim/nano, git commit without -m, python REPL.\n\n"
        f"command:\n{command}"
    )


def _confirm_sensitive_command(command: str) -> bool:
    confirm_sensitive(command)
    answer = input(confirm_prompt()).strip().lower()
    return answer == "yes"


@tool
def save_text_to_file(data: str, filename: str = "research_output.txt") -> str:
    """Persist text to a file on disk. Use when the user wants results saved.
    Pass the full research content as data and a descriptive filename."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    formatted_text = f"--- Research Output ---\nTimestamp: {timestamp}\n\n{data}\n\n"

    output_dir = Path("data")
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / filename

    with open(filepath, "a", encoding="utf-8") as f:
        f.write(formatted_text)

    return f"Data successfully saved to {filepath}"


def _format_shell_result(command: str, output: str, exit_code: int) -> str:
    parts = [
        f"shell: persistent system shell ({platform.system()}, project venv not active)",
        f"exit_code: {exit_code}",
    ]
    if output:
        parts.append(f"output:\n{output.rstrip()}")
    else:
        parts.append("(no output)")
    parts.append(f"command:\n{command}")
    return "\n\n".join(parts)


@tool
def terminal_run(command: str) -> str:
    """Run a command in a persistent system shell and return combined output and exit code.

    The shell keeps state across calls (e.g. cd persists). It runs outside the
    project's Python venv so system tools and packages are visible. stdout and
    stderr are merged in the output.

    Interactive commands (gh auth login, ssh, editors, REPLs, etc.) are refused —
    tell the user to run those in their own terminal.

    Sensitive commands (git push, rm, sudo, package installs, etc.) are blocked
    until the user types 'yes' at an interactive prompt."""
    if _is_interactive_command(command):
        shell_blocked("interactive", command)
        return _interactive_block_message(command)

    if _is_sensitive_command(command) and not _confirm_sensitive_command(command):
        shell_blocked("denied", command)
        return (
            "exit_code: blocked\n\n"
            "Command not run: user denied permission.\n\n"
            f"command:\n{command}"
        )

    shell_running(command)
    try:
        output, exit_code = get_shell().run(command)
    except RuntimeError as exc:
        shell_done(-1, 0)
        return f"exit_code: error\n\n{exc}\n\ncommand:\n{command}"

    line_count = 0 if not output else len(output.splitlines())
    shell_done(exit_code, line_count)
    return _format_shell_result(command, output, exit_code)


@tool
def file_read(filepath: str) -> str:
    """Read the contents of a file and return the output. This uses the Pathlib library to read the file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


@tool
def file_write(filepath: str, content: str) -> str:
    """Write to a file and return the output. This uses the Pathlib library to write to the file."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return f"File {filepath} successfully written."


@tool
def remember_project(text: str) -> str:
    """Commit a durable, self-contained fact about this repo to Cognee project memory.

    REQUIRED when the user asks you to remember/save/note something about this repo.
    Also use proactively for durable repo facts when appropriate. Pass a complete
    statement (not chat shorthand). Not for secrets or machine-wide facts."""
    return _remember_project(text)


@tool
def remember_device(text: str) -> str:
    """Commit a durable, self-contained fact about this machine to Cognee device memory.

    REQUIRED when the user asks you to remember/save/note something about this machine.
    Also use proactively for durable machine facts when appropriate. Pass a complete
    statement (not chat shorthand). Not for secrets or repo-specific facts."""
    return _remember_device(text)


@tool
def recall_project(query: str) -> str:
    """Search Cognee project memory for facts about this repo.

    Call before remember_project when the user asks about prior repo context, or
    to avoid storing duplicate facts."""
    return _recall_project(query)


@tool
def recall_device(query: str) -> str:
    """Search Cognee device memory for facts about this machine.

    Call before remember_device when the user asks about machine setup or prefs,
    or to avoid storing duplicate facts."""
    return _recall_device(query)
