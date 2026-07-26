"""SQLite session persistence for chat history (LangGraph checkpointer)."""

import hashlib
import os
import sqlite3
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from shellie.paths import project_session_db

_INTERRUPT_TOOL_CONTENT = "Interrupted by user — tool did not finish."

# Max graph steps per user turn (model call and tool round each count).
# ~40 ≈ enough for a multi-file edit job; stops endless rewrite loops.
# Override with AGENT_RECURSION_LIMIT. LangGraph default is 25 if unset here.
DEFAULT_RECURSION_LIMIT = 40


def project_thread_id(project_root: Path) -> str:
    """Stable session key for one project directory (used as LangGraph thread_id)."""
    path = str(project_root.resolve())
    return hashlib.sha256(path.encode()).hexdigest()[:16]


def open_session_checkpointer(project_root: Path) -> SqliteSaver:
    """Open (or create) the per-project session.sqlite checkpointer."""
    db_path = project_session_db(project_root)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()
    return checkpointer


def _recursion_limit(explicit: int | None = None) -> int:
    if explicit is not None:
        return explicit
    raw = os.getenv("AGENT_RECURSION_LIMIT", "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    return DEFAULT_RECURSION_LIMIT


def session_config(thread_id: str, *, recursion_limit: int | None = None) -> dict:
    """LangGraph config — one thread_id plus a per-turn step cap."""
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": _recursion_limit(recursion_limit),
    }


def clear_session(checkpointer: SqliteSaver, thread_id: str) -> None:
    """Remove all checkpointed messages for this project session."""
    checkpointer.delete_thread(thread_id)


def session_message_count(agent, config: dict) -> int:
    """How many messages are already stored for this session (0 if new)."""
    try:
        snapshot = agent.get_state(config)
    except Exception:
        return 0
    if not snapshot or not snapshot.values:
        return 0
    return len(snapshot.values.get("messages", []))


def _tool_call_id_and_name(tc) -> tuple[str | None, str]:
    if isinstance(tc, dict):
        return tc.get("id"), tc.get("name") or "tool"
    return getattr(tc, "id", None), getattr(tc, "name", None) or "tool"


def repair_dangling_tool_calls(agent, config: dict) -> int:
    """Append synthetic ToolMessages for any open tool_calls in the checkpoint.

    After Ctrl+C mid-tool, the last AIMessage may have tool_calls without matching
    ToolMessages — the next model call then 400s. Returns how many were closed.
    """
    try:
        snapshot = agent.get_state(config)
    except Exception:
        return 0
    if not snapshot or not snapshot.values:
        return 0
    messages = snapshot.values.get("messages") or []
    if not messages:
        return 0

    answered: set[str] = set()
    for msg in messages:
        if isinstance(msg, ToolMessage):
            tid = getattr(msg, "tool_call_id", None)
            if tid:
                answered.add(tid)

    pending: list[ToolMessage] = []
    for msg in messages:
        if not isinstance(msg, AIMessage) or not msg.tool_calls:
            continue
        for tc in msg.tool_calls:
            tc_id, name = _tool_call_id_and_name(tc)
            if tc_id and tc_id not in answered:
                pending.append(
                    ToolMessage(
                        content=_INTERRUPT_TOOL_CONTENT,
                        tool_call_id=tc_id,
                        name=name,
                    )
                )
                answered.add(tc_id)

    if not pending:
        return 0
    try:
        agent.update_state(config, {"messages": pending})
    except Exception:
        return 0
    return len(pending)
