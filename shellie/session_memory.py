"""SQLite session persistence for chat history (LangGraph checkpointer)."""

import hashlib
import os
import sqlite3
from pathlib import Path
from typing import NamedTuple

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from shellie.paths import project_session_db

_INTERRUPT_TOOL_CONTENT = "Interrupted by user — tool did not finish."

# create_agent graph node that normally appends ToolMessages.
_TOOLS_NODE = "tools"

# Max graph steps per user turn (model call and tool round each count).
# ~40 ≈ enough for a multi-file edit job; stops endless rewrite loops.
# Override with AGENT_RECURSION_LIMIT. LangGraph default is 25 if unset here.
DEFAULT_RECURSION_LIMIT = 40


class RepairResult(NamedTuple):
    """Outcome of repair_dangling_tool_calls."""

    closed: int
    remaining: int = 0
    error: str | None = None


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
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else None
        name = tc.get("name") or (fn.get("name") if fn else None) or "tool"
        return tc.get("id"), name
    return getattr(tc, "id", None), getattr(tc, "name", None) or "tool"


def _is_ai_message(msg) -> bool:
    if isinstance(msg, AIMessage):
        return True
    return type(msg).__name__ in ("AIMessage", "AIMessageChunk")


def _is_tool_message(msg) -> bool:
    if isinstance(msg, ToolMessage):
        return True
    return type(msg).__name__ == "ToolMessage"


def _message_tool_calls(msg) -> list:
    """Tool calls on an AI message (attribute or additional_kwargs)."""
    calls = getattr(msg, "tool_calls", None) or []
    if calls:
        return list(calls)
    extra = getattr(msg, "additional_kwargs", None) or {}
    if isinstance(extra, dict):
        raw = extra.get("tool_calls") or []
        if raw:
            return list(raw)
    return []


def _session_messages(agent, config: dict) -> list:
    """Return checkpoint messages (empty if none). Raises on get_state failure."""
    snapshot = agent.get_state(config)
    if not snapshot or not snapshot.values:
        return []
    return list(snapshot.values.get("messages") or [])


def _dangling_tool_messages(messages: list) -> list[ToolMessage]:
    """Build synthetic ToolMessages for every unanswered tool_call id."""
    answered: set[str] = set()
    for msg in messages:
        if _is_tool_message(msg):
            tid = getattr(msg, "tool_call_id", None)
            if tid:
                answered.add(str(tid))

    pending: list[ToolMessage] = []
    for msg in messages:
        if not _is_ai_message(msg):
            continue
        for tc in _message_tool_calls(msg):
            tc_id, name = _tool_call_id_and_name(tc)
            if tc_id and str(tc_id) not in answered:
                tid = str(tc_id)
                pending.append(
                    ToolMessage(
                        content=_INTERRUPT_TOOL_CONTENT,
                        tool_call_id=tid,
                        name=name or "tool",
                    )
                )
                answered.add(tid)
    return pending


def count_dangling_tool_calls(agent, config: dict) -> int:
    """How many tool_call ids still lack a ToolMessage (-1 if unreadable)."""
    try:
        messages = _session_messages(agent, config)
    except Exception:
        return -1
    return len(_dangling_tool_messages(messages))


def repair_dangling_tool_calls(agent, config: dict) -> RepairResult:
    """Append synthetic ToolMessages for any open tool_calls in the checkpoint.

    After Ctrl+C mid-tool, an AIMessage may have tool_calls without matching
    ToolMessages — the next model call then 400s. Uses as_node='tools' so the
    graph treats the append like a normal tools-node write, then re-reads state
    to verify nothing is still dangling.
    """
    try:
        messages = _session_messages(agent, config)
    except Exception as exc:
        return RepairResult(closed=0, remaining=-1, error=f"get_state failed: {exc}")

    pending = _dangling_tool_messages(messages)
    if not pending:
        return RepairResult(closed=0, remaining=0)

    try:
        agent.update_state(config, {"messages": pending}, as_node=_TOOLS_NODE)
    except TypeError:
        # Older langgraph without as_node kw — fall back.
        try:
            agent.update_state(config, {"messages": pending})
        except Exception as exc:
            return RepairResult(
                closed=0,
                remaining=len(pending),
                error=f"update_state failed: {exc}",
            )
    except Exception as exc:
        return RepairResult(
            closed=0,
            remaining=len(pending),
            error=f"update_state failed: {exc}",
        )

    try:
        after = _session_messages(agent, config)
        still = _dangling_tool_messages(after)
    except Exception as exc:
        return RepairResult(
            closed=len(pending),
            remaining=-1,
            error=f"verify get_state failed: {exc}",
        )

    if still:
        return RepairResult(
            closed=max(0, len(pending) - len(still)),
            remaining=len(still),
            error=(
                f"still {len(still)} open tool call(s) after repair — try /clear"
            ),
        )
    return RepairResult(closed=len(pending), remaining=0)
