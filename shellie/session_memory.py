"""SQLite session persistence for chat history (LangGraph checkpointer)."""

import hashlib
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from shellie.paths import project_session_db


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


def session_config(thread_id: str) -> dict:
    """LangGraph config dict — ties each conversation to one thread_id."""
    return {"configurable": {"thread_id": thread_id}}


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
