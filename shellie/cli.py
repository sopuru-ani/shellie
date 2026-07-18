"""CLI entry point for shellie."""

import shlex
import subprocess
from pathlib import Path

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from shellie.agent import build_agent
from shellie.cognee_memory import cognee_status_message, init_cognee_memory
from shellie.config import bootstrap
from shellie.images import encode_image_ref, looks_like_image_ref
from shellie.paths import DEVICE_CONFIG_DIR, project_agent_dir, project_session_db
from shellie.shell import close_shell, system_shell_env
from shellie.tools import clear_approved_commands
from shellie.session_memory import clear_session, session_message_count
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


def _format_run_error(exc: BaseException) -> str:
    """One-line user message for a failed agent turn (keeps the REPL alive)."""
    text = str(exc).strip() or type(exc).__name__
    first = text.splitlines()[0]
    if len(first) > 200:
        first = first[:197] + "..."
    lowered = first.lower()
    name = type(exc).__name__
    if name == "GraphRecursionError" or "recursion limit" in lowered:
        return (
            f"Error: hit the step limit for this turn ({first}). "
            "Send another message (e.g. continue) to keep going."
        )
    if (
        "resourceexhausted" in lowered
        or "rate limit" in lowered
        or "429" in lowered
        or "total request limit" in lowered
    ):
        return (
            f"Error: provider rate/worker limit hit ({first}). "
            "Try again in a moment."
        )
    return f"Error: {first}"


def _split_command_args(rest: str) -> list[str]:
    """Split a command's argument string, tolerating Windows backslash paths."""
    try:
        return shlex.split(rest, posix=False)
    except ValueError:
        return rest.split()


def _print_images(pending_images: list[str]) -> None:
    if not pending_images:
        print("No images attached.")
        return
    print(f"Attached images ({len(pending_images)}):")
    for i, ref in enumerate(pending_images, 1):
        print(f"  {i}. {ref}")


def _extract_auto_images(query: str) -> list[str]:
    """Pull image-looking path/URL tokens out of a normal chat message."""
    found: list[str] = []
    for token in _split_command_args(query):
        cleaned = token.strip().strip('"').strip("'")
        if cleaned and looks_like_image_ref(cleaned):
            found.append(cleaned)
    return found


def _build_message_content(query: str, pending_images: list[str]):
    """Text-only string when no images; otherwise a multimodal content list.

    References are encoded on the fly here (not persisted), so session.sqlite only
    ever stores the resulting message — we pass encoded data URIs to the model but
    keep the buffer as plain path/URL strings.
    """
    if not pending_images:
        return query, []
    content = [{"type": "text", "text": query}]
    errors: list[str] = []
    for ref in pending_images:
        data_uri, error = encode_image_ref(ref)
        if error:
            errors.append(f"{ref}: {error}")
            continue
        content.append({"type": "image_url", "image_url": {"url": data_uri}})
    # If every image failed, fall back to text so the turn still runs.
    if len(content) == 1:
        return query, errors
    return content, errors


def run_repl(project_root: Path) -> None:
    agent, session_config, checkpointer, thread_id = build_agent(project_root)

    pending_images: list[str] = []

    print("Tool and shell activity print as they run. Set AGENT_DEBUG=1 for raw LangChain logs.\n")
    print("Commands: /shell, /shell <cmd>, /chat (in shell mode), /clear, /bye")
    print("Images:   /image <path|url> [question], /attach <path|url>, /images, /images clear, /detach <n>\n")
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
            pending_images.clear()
            clear_approved_commands()
            print("Session cleared.")
            continue

        stripped = query.strip()

        if stripped == "/images":
            _print_images(pending_images)
            continue

        if stripped == "/images clear":
            pending_images.clear()
            print("Cleared all attached images.")
            continue

        if stripped.startswith("/detach"):
            args = _split_command_args(stripped[len("/detach"):])
            if len(args) != 1 or not args[0].isdigit():
                print("Usage: /detach <number>  (see /images)")
                continue
            idx = int(args[0])
            if 1 <= idx <= len(pending_images):
                removed = pending_images.pop(idx - 1)
                print(f"Detached {idx}: {removed}")
            else:
                print(f"No image #{idx}. There are {len(pending_images)} attached.")
            continue

        if stripped.startswith("/attach"):
            args = _split_command_args(stripped[len("/attach"):])
            if not args:
                print("Usage: /attach <path|url>")
                continue
            for ref in args:
                pending_images.append(ref)
                print(f"Attached: {ref}")
            continue

        if stripped.startswith("/image"):
            rest = stripped[len("/image"):].lstrip()
            if not rest:
                print("Usage: /image <path|url> [question]")
                continue
            # First token is the path/URL (quoted if it has spaces); the rest is the question.
            if rest[0] in ("'", '"'):
                quote = rest[0]
                end = rest.find(quote, 1)
                if end == -1:
                    ref, question = rest[1:], ""
                else:
                    ref, question = rest[1:end], rest[end + 1:].strip()
            else:
                parts = rest.split(None, 1)
                ref = parts[0]
                question = parts[1].strip() if len(parts) > 1 else ""
            pending_images.append(ref)
            print(f"Attached: {ref}")
            if not question:
                # Attach only; wait for the next message to ask.
                continue
            query = question

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

        # Auto-detect: pull image-looking paths/URLs out of a normal message.
        if not query.startswith("/"):
            for ref in _extract_auto_images(query):
                if ref not in pending_images:
                    pending_images.append(ref)
                    print(f"Auto-attached image: {ref}")

        message_content, image_errors = _build_message_content(query, pending_images)
        for err in image_errors:
            print(f"Image skipped — {err}")

        # New user turn: prior plan approvals do not carry over.
        clear_approved_commands()

        prev_count = session_message_count(agent, session_config)

        final_state = None
        # Token stream bookkeeping: only show the user-facing answer, not tool-planning calls.
        # Hold every model text chunk until that message finishes without tool calls — including
        # after earlier tool rounds. Streaming mid-message used to open ── reply ── while the
        # agent was still about to call more tools.
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
            # Clear again in case tool activity restored the status after reply opened.
            working_clear()
            open_reply()
            print(text, end="", flush=True)

        def flush_pending() -> None:
            nonlocal pending_text
            if pending_text and not msg_is_tool:
                write_reply("".join(pending_text))
            pending_text = []

        working_show()
        run_error: str | None = None
        try:
            for chunk in agent.stream(
                {"messages": [HumanMessage(content=message_content)]},
                config=session_config,
                stream_mode=["updates", "messages", "values"],
            ):
                mode, payload = chunk
                if mode == "updates":
                    _print_stream_updates(payload)
                elif mode == "messages":
                    token, _metadata = payload
                    # Tool results also arrive on this channel — never print them.
                    if not _is_ai_stream_token(token):
                        continue

                    tid = getattr(token, "id", None)
                    if tid != msg_id:
                        # Previous model call finished. If it had no tools, that text is the answer
                        # (casual chat, or the final message after a tool loop).
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

                    # Hold until this message ends without tools (same before and after tool rounds).
                    pending_text.append(text)
                elif mode == "values":
                    final_state = payload

            # End of stream: flush a no-tool answer that never got a msg_id change.
            if not msg_is_tool:
                flush_pending()
        except KeyboardInterrupt:
            run_error = "Interrupted."
        except Exception as exc:
            run_error = _format_run_error(exc)
        finally:
            working_clear()

        if run_error is not None:
            if reply_open:
                print()
                agent_reply_end()
            print(run_error)
            continue

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
