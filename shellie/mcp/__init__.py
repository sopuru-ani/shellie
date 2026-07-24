"""Optional MCP client support (shellie[mcp])."""

from shellie.mcp.catalog import (
    catalog_server_names,
    connection_for_server,
    get_catalog_entry,
)
from shellie.mcp.config import (
    enabled_server_names,
    ensure_mcp_config,
    is_server_enabled,
    known_server_names,
    mcp_config_path,
    set_server_enabled,
)
from shellie.mcp.client import McpLoadResult, load_mcp_tools
from shellie.mcp.mcp import mcp_available, mcp_enabled, mcp_status_message

__all__ = [
    "catalog_server_names",
    "connection_for_server",
    "enabled_server_names",
    "ensure_mcp_config",
    "get_catalog_entry",
    "is_server_enabled",
    "known_server_names",
    "load_mcp_tools",
    "mcp_available",
    "McpLoadResult",
    "mcp_config_path",
    "mcp_enabled",
    "mcp_status_message",
    "set_server_enabled",
]
