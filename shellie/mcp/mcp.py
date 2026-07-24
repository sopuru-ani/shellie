"""MCP client availability and status (optional shellie[mcp] extra).

Installed = langchain-mcp-adapters is importable.
Enabled = MCP_ENABLED is truthy in the environment.
Server enable/disable lives in ~/.config/shellie/mcp.json (see config.py).
"""

from __future__ import annotations

import os

from shellie.mcp.config import enabled_server_names

_mcp_available: bool | None = None


def _env_truthy(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def mcp_available() -> bool:
    """Whether langchain-mcp-adapters is installed (shellie[mcp] / pipx inject)."""
    global _mcp_available
    if _mcp_available is None:
        try:
            import langchain_mcp_adapters  # noqa: F401
        except ImportError:
            _mcp_available = False
        else:
            _mcp_available = True
    return _mcp_available


def mcp_enabled() -> bool:
    """Installed and explicitly turned on via MCP_ENABLED."""
    if not mcp_available():
        return False
    return _env_truthy("MCP_ENABLED", default=False)


def mcp_status_message() -> str:
    """One-line status for the REPL banner (same role as cognee_status_message)."""
    if not mcp_available():
        return (
            "not installed — install with: pip install 'shellie[mcp]' "
            "or: pipx inject shellie langchain-mcp-adapters"
        )
    if not mcp_enabled():
        return "disabled — set MCP_ENABLED=1 in .env (device or project)"
    enabled = enabled_server_names()
    if not enabled:
        return "client ready — no mcp servers enabled"
    return "client ready — " + ", ".join(enabled)
