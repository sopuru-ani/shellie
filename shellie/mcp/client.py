"""Load LangChain tools from enabled MCP servers (device mcp.json + catalog).

Requires shellie[mcp] (langchain-mcp-adapters). Call load_mcp_tools() from the
agent after bootstrap() so .env tokens are available.

MCP tools from the adapter are async-only (coroutine=, no func=). Shellie's
agent uses sync stream/invoke, so we attach a sync wrapper after load.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass, field
from typing import Any

from shellie.mcp.catalog import connection_for_server
from shellie.mcp.config import enabled_server_names
from shellie.mcp.mcp import mcp_available, mcp_enabled


@dataclass
class McpLoadResult:
    """Tools from MCP plus human-readable notes for the banner / logs."""

    tools: list[Any] = field(default_factory=list)
    connected: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.tools) and not self.errors

    def summary(self) -> str:
        if not mcp_available():
            return "not installed"
        if not mcp_enabled():
            return "disabled"
        if not self.connected and not self.errors:
            return "no mcp servers enabled"
        parts: list[str] = []
        if self.connected:
            parts.append(
                f"connected: {', '.join(self.connected)} ({len(self.tools)} tools)"
            )
        for err in self.errors:
            parts.append(f"error: {err}")
        return "; ".join(parts)


def build_mcp_connections() -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Build MultiServerMCPClient connection map for enabled curated servers.

    Returns (connections, errors). Servers that fail (e.g. missing PAT) are
    skipped and listed in errors so other servers can still load.
    """
    connections: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for name in enabled_server_names():
        try:
            connections[name] = connection_for_server(name)
        except ValueError as exc:
            errors.append(str(exc))
    return connections, errors


def _run_async(coro: Any) -> Any:
    """Drive an async MCP coroutine to completion from sync tool invoke."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # A loop is already running — asyncio.run would fail; use a fresh thread.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _with_sync_invoke(tool: Any) -> Any:
    """Attach a sync func= when the MCP tool only exposes coroutine=.

    Shellie builtins already have sync funcs — getattr checks skip those if
    they ever passed through here. MCP adapter tools typically have coroutine
    only, which is what caused NotImplementedError on sync invoke.
    """
    if getattr(tool, "func", None) is not None:
        return tool

    coro_fn = getattr(tool, "coroutine", None)
    if coro_fn is None:
        return tool

    def sync_fn(*args: Any, **kwargs: Any) -> Any:
        return _run_async(coro_fn(*args, **kwargs))

    from langchain_core.tools import StructuredTool

    return StructuredTool(
        name=tool.name,
        description=tool.description or "",
        args_schema=tool.args_schema,
        coroutine=coro_fn,
        func=sync_fn,
        response_format=getattr(tool, "response_format", "content_and_artifact"),
        metadata=getattr(tool, "metadata", None),
        handle_tool_error=getattr(tool, "handle_tool_error", False),
    )


def _ensure_sync_tools(tools: list[Any]) -> list[Any]:
    return [_with_sync_invoke(t) for t in tools]


async def _load_tools_async(
    connections: dict[str, dict[str, Any]],
) -> list[Any]:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(
        connections,
        tool_name_prefix=True,  # github_list_issues vs collisions later
    )
    return await client.get_tools()


def load_mcp_tools() -> McpLoadResult:
    """Sync entry: load tools from all enabled MCP servers, or an empty result.

    Safe to call when MCP is off or not installed — returns empty tools.
    """
    result = McpLoadResult()
    if not mcp_available() or not mcp_enabled():
        return result

    connections, errors = build_mcp_connections()
    result.errors.extend(errors)
    if not connections:
        return result

    try:
        tools = asyncio.run(_load_tools_async(connections))
    except Exception as exc:  # network / auth / adapter failures
        result.errors.append(f"failed to load MCP tools: {exc}")
        return result

    result.tools = _ensure_sync_tools(list(tools))
    result.connected = sorted(connections.keys())
    return result
