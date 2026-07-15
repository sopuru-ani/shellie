"""CLI entry point for shellie."""

import subprocess
from pathlib import Path

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from shellie.agent import build_agent
from shellie.cognee_memory import cognee_status_message, init_cognee_memory
from shellie.config import bootstrap
from shellie.paths import DEVICE_CONFIG_DIR, project_agent_dir, project_session_db
from shellie.session_memory import clear_session, session_message_count
from shellie.shell import close_shell, system_shell_env
from shellie.ui import (
    agent_calling_tool,
    agent_reply_end,
    agent_reply_start,
    working_clear,
    working_show,
)


def _print_stream_updates(event: dict) -> bool:
    """Print tool calls from an updates event. Returns True if any tool was requested."""
    saw_tool = False
    for update in event.values():
        if not isinstance(update, dict):
            continue
        for msg in update.get("messages", []):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                saw_tool = True
                for tc in msg.tool_calls:
                    agent_calling_tool(tc["name"], tc.get("args", {}))
    return saw_tool


def _is_ai_stream_token(token) -> bool:
    """True only for model tokens — never ToolMessage / tool result payloads."""
    if isinstance(token, AIMessageChunk):
        return True
    # Rare: some stacks emit a full AIMessage on the messages channel.
    if isinstance(token, AIMessage):
        return True
    name = type(token).__name__
    return name in ("AIMessageChunk", "AIMessage")


def _chunk_text(content) -> str:
    """Normalize AIMessageChunk.content to a printable string."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
            else:
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)
        return "".join(parts)
    return ""


def _latest_reply(new_messages: list) -> str | None:
    """Last assistant text that is not a tool-calling step."""
    for msg in reversed(new_messages):
        if not isinstance(msg, AIMessage):
            continue
        if getattr(msg, "tool_calls", None):
            continue
        text = _chunk_text(msg.content)
        if text:
            return text
    return None


def _warn_missing_env(project_root: Path) -> None:
    env_file = project_root / ".env"
    if not env_file.is_file():
        print(
            f"Warning: no .env in {project_root}\n"
            "  Copy .env.example from the shellie repo into this project and set your API keys.\n"
        )


def run_repl(project_root: Path) -> None:
    agent, session_config, checkpointer, thread_id = build_agent(project_root)

    print("Tool and shell activity print as they run. Set AGENT_DEBUG=1 for raw LangChain logs.\n")
    print("Commands: /shell, /shell <cmd>, /chat (in shell mode), /clear, /bye\n")
    print(f"Project root:  {project_root}")
    print(f"Config:        {project_root / '.env'}")
    print(f"Project data:  {project_agent_dir(project_root)}  (session + Cognee project tier)")
    print(f"Device data:   {DEVICE_CONFIG_DIR}  (Cognee device tier)")
    print(f"Cognee:        {cognee_status_message()}")
    stored = session_message_count(agent, session_config)
    if stored:
        print(f"Session:       resuming ({stored} messages in {project_session_db(project_root).name})")
    else:
        print(f"Session:       new ({project_session_db(project_root).name})")
    print()

    while True:
        query = input("~>: ")
        if query.strip() == "/bye":
            close_shell()
            checkpointer.conn.close()
            break

        if query.strip() == "/clear":
            clear_session(checkpointer, thread_id)
            print("Session cleared.")
            continue

        if query.strip() == "/shell":
            print("Shell mode - type /chat to return to chat mode. Each line runs in a fresh subshell")
            while True:
                line = input("(shell)$")
                if line.strip() == "/chat":
                    break
                if line.strip():
                    subprocess.run(line, shell=True, env=system_shell_env())
            continue

        if query.startswith("/shell "):
            command = query[len("/shell ") :].strip()
            if not command:
                print("Usage: /shell <command>")
                continue
            subprocess.run(command, shell=True, env=system_shell_env())
            continue

        prev_count = session_message_count(agent, session_config)

        final_state = None
        # Token stream bookkeeping: only show the user-facing answer, not tool-planning calls.
        tools_used = False
        reply_open = False
        msg_id = None
        msg_is_tool = False
        pending_text: list[str] = []

        def open_reply() -> None:
            nonlocal reply_open
            if not reply_open:
                # agent_reply_start clears the sticky working line.
                agent_reply_start()
                reply_open = True

        def write_reply(text: str) -> None:
            if not text:
                return
            open_reply()
            print(text, end="", flush=True)

        def flush_pending() -> None:
            nonlocal pending_text
            if pending_text and not msg_is_tool:
                write_reply("".join(pending_text))
            pending_text = []

        working_show()
        try:
            for chunk in agent.stream(
                {"messages": [HumanMessage(content=query)]},
                config=session_config,
                stream_mode=["updates", "messages", "values"],
            ):
                mode, payload = chunk
                if mode == "updates":
                    if _print_stream_updates(payload):
                        tools_used = True
                elif mode == "messages":
                    token, _metadata = payload
                    # Tool results also arrive on this channel — never print them.
                    if not _is_ai_stream_token(token):
                        continue

                    tid = getattr(token, "id", None)
                    if tid != msg_id:
                        # Previous model call finished. If it had no tools, that text is the answer
                        # (e.g. casual chat with zero tools).
                        if msg_id is not None and not msg_is_tool:
                            flush_pending()
                        msg_id = tid
                        msg_is_tool = False
                        pending_text = []

                    tool_chunks = getattr(token, "tool_call_chunks", None) or []
                    tool_calls = getattr(token, "tool_calls", None) or []
                    if tool_chunks or tool_calls:
                        msg_is_tool = True
                        pending_text = []
                        continue

                    text = _chunk_text(getattr(token, "content", None))
                    if not text or msg_is_tool:
                        continue

                    if tools_used:
                        # Post-tool model call → stream tokens live as the final answer.
                        write_reply(text)
                    else:
                        # Might still decide to call tools; hold text until we know.
                        pending_text.append(text)
                elif mode == "values":
                    final_state = payload

            # End of stream: flush a no-tool answer that never got a msg_id change.
            if not msg_is_tool:
                flush_pending()
        finally:
            working_clear()

        if reply_open:
            print()
            agent_reply_end()
            continue

        if final_state is None:
            print("Error: agent produced no response.")
            continue

        # Fallback if the provider did not stream message tokens.
        reply = _latest_reply(final_state["messages"][prev_count:])
        if reply:
            agent_reply_start()
            print(reply)
            agent_reply_end()


def main() -> None:
    project_root = bootstrap()
    _warn_missing_env(project_root)
    init_cognee_memory(project_root)
    run_repl(project_root)


if __name__ == "__main__":
    main()
