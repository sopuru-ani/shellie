"""Curated MCP server connection recipes (no secrets).

config.py stores which servers are enabled on this device.
This module maps server id → how MultiServerMCPClient should connect.
Tokens come from the environment (device/project .env), never from mcp.json.
"""

from __future__ import annotations

import os
from typing import Any

# Remote GitHub MCP (hosted). PAT (Personal Access Token) auth — OAuth is Copilot/host oriented.
# https://github.com/github/github-mcp-server
GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"
GITHUB_TOKEN_ENV = "GITHUB_PERSONAL_ACCESS_TOKEN"

# name -> static recipe (transport + url + which env holds the token)
_CATALOG: dict[str, dict[str, Any]] = {
    "github": {
        "transport": "http",
        "url": GITHUB_MCP_URL,
        "token_env": GITHUB_TOKEN_ENV,
        "description": "GitHub remote MCP (repos, issues, PRs, ...)",
        # Auth recipe for shellie-mcp enable (other servers can use different auth later)
        "auth": "pat",
        "pat_create_url": "https://github.com/settings/personal-access-tokens/new",
        "pat_hint": (
            "Create a fine-grained PAT (or classic with repo scope). "
            "Shellie stores it in ~/.config/shellie/.env as GITHUB_PERSONAL_ACCESS_TOKEN."
        ),
        "validate_url": "https://api.github.com/user",
    },
}


def catalog_server_names() -> list[str]:
    return sorted(_CATALOG.keys())


def get_catalog_entry(name: str) -> dict[str, Any] | None:
    """Return a copy of the catalog entry, or None if unknown."""
    entry = _CATALOG.get(name.strip().casefold())
    if entry is None:
        return None
    return dict(entry)


def connection_for_server(name: str) -> dict[str, Any]:
    """Build a MultiServerMCPClient connection dict for a curated server.

    Raises ValueError if the server is unknown or the required token env is missing.
    """
    key = name.strip().casefold()
    entry = _CATALOG.get(key)
    if entry is None:
        known = ", ".join(catalog_server_names())
        raise ValueError(f"Unknown MCP server {name!r}. Known: {known}")

    transport = entry["transport"]
    if transport == "http":
        token_env = entry["token_env"]
        token = (os.getenv(token_env) or "").strip()
        if not token:
            raise ValueError(
                f"MCP server {key!r} needs {token_env} in the environment "
                f"(set it in ~/.config/shellie/.env or the project .env)."
            )
        return {
            "transport": "http",
            "url": entry["url"],
            "headers": {"Authorization": f"Bearer {token}"},
        }

    raise ValueError(f"Unsupported transport {transport!r} for MCP server {key!r}")
