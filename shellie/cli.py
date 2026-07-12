"""CLI entry point for shellie."""

import subprocess
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from shellie.agent import build_agent
from shellie.cognee_memory import cognee_status_message, init_cognee_memory
from shellie.config import bootstrap
from shellie.paths import DEVICE_CONFIG_DIR, project_agent_dir, project_session_db
from shellie.session_memory import clear_session, session_message_count
from shellie.shell import close_shell, system_shell_env
from shellie.ui import agent_calling_tool, agent_reply_start


def _print_stream_updates(event: dict) -> None:
    for update in event.values():
        if not isinstance(update, dict):
            continue
        for msg in update.get("messages", []):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    agent_calling_tool(tc["name"], tc.get("args", {}))


def _latest_reply(new_messages: list) -> str | None:
    for msg in reversed(new_messages):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content
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
        for chunk in agent.stream(
            {"messages": [HumanMessage(content=query)]},
            config=session_config,
            stream_mode=["updates", "values"],
        ):
            mode, payload = chunk
            if mode == "updates":
                _print_stream_updates(payload)
            elif mode == "values":
                final_state = payload

        if final_state is None:
            print("Error: agent produced no response.")
            continue

        reply = _latest_reply(final_state["messages"][prev_count:])
        if reply:
            agent_reply_start()
            print(reply)


def main() -> None:
    project_root = bootstrap()
    _warn_missing_env(project_root)
    init_cognee_memory(project_root)
    run_repl(project_root)


if __name__ == "__main__":
    main()
