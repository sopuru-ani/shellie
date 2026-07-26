"""Optional MCP client support (shellie[mcp])."""

from shellie.mcp.catalog import (
    catalog_server_names,
    connection_for_server,
    get_catalog_entry,
)
from shellie.mcp.client import McpLoadResult, load_mcp_tools
from shellie.mcp.config import (
    custom_mcp_config_path,
    enabled_custom_server_names,
    enabled_server_names,
    ensure_custom_mcp_config,
    ensure_mcp_config,
    is_custom_server_enabled,
    is_server_enabled,
    known_custom_server_names,
    known_server_names,
    mcp_config_path,
    set_custom_server_enabled,
    set_server_enabled,
)
from shellie.mcp.custom_catalog import (
    connection_for_custom_server,
    custom_catalog_server_names,
    custom_mcp_catalog_path,
    custom_mcp_servers_dir,
    get_custom_catalog_entry,
    register_new_custom_server,
    remove_custom_catalog_entry,
    upsert_custom_catalog_entry,
)
from shellie.mcp.mcp import mcp_available, mcp_enabled, mcp_status_message

__all__ = [
    # Curated catalog + toggles
    "catalog_server_names",
    "connection_for_server",
    "enabled_server_names",
    "ensure_mcp_config",
    "get_catalog_entry",
    "is_server_enabled",
    "known_server_names",
    "mcp_config_path",
    "set_server_enabled",
    # Custom catalog + toggles
    "connection_for_custom_server",
    "custom_catalog_server_names",
    "custom_mcp_catalog_path",
    "custom_mcp_config_path",
    "custom_mcp_servers_dir",
    "enabled_custom_server_names",
    "ensure_custom_mcp_config",
    "get_custom_catalog_entry",
    "is_custom_server_enabled",
    "known_custom_server_names",
    "register_new_custom_server",
    "remove_custom_catalog_entry",
    "set_custom_server_enabled",
    "upsert_custom_catalog_entry",
    # Client + status
    "load_mcp_tools",
    "mcp_available",
    "McpLoadResult",
    "mcp_enabled",
    "mcp_status_message",
]
