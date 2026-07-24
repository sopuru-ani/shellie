"""Load LangChain tools from enabled MCP servers (device mcp.json + catalog).

Requires shellie[mcp] (langchain-mcp-adapters). Call load_mcp_tools() from the
agent after bootstrap() so .env tokens are available.
"""

from __future__ import annotations

import asyncio
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

    result.tools = list(tools)
    result.connected = sorted(connections.keys())
    return result
