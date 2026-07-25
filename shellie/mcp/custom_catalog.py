"""Device-level custom MCP connection recipes (~/.config/shellie/mcp_custom_catalog.json).

Enable toggles live in mcp_custom.json (config.py).
This file stores how to spawn each custom server (usually stdio + venv python).

Example entry:
  {
    "servers": {
      "weather": {
        "transport": "stdio",
        "command": "C:/Users/you/.config/shellie/mcp_servers/weather/.venv/Scripts/python.exe",
        "args": ["C:/Users/you/.config/shellie/mcp_servers/weather/server.py"],
        "description": "Local weather tools"
      }
    }
  }

Secrets stay out of this file — use the server's own .env or optional env var *names*
resolved at connect time (see connection_for_custom_server).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from shellie.mcp.config import known_server_names
from shellie.paths import DEVICE_CONFIG_DIR


def custom_mcp_catalog_path() -> Path:
    return DEVICE_CONFIG_DIR / "mcp_custom_catalog.json"


def custom_mcp_servers_dir() -> Path:
    """Default root for generated local MCP server projects."""
    return DEVICE_CONFIG_DIR / "mcp_servers"


def _default_catalog() -> dict[str, Any]:
    return {"servers": {}}


def ensure_custom_mcp_catalog() -> Path:
    DEVICE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = custom_mcp_catalog_path()
    if not path.is_file():
        save_custom_mcp_catalog(_default_catalog())
    return path


def load_custom_mcp_catalog() -> dict[str, Any]:
    """Load mcp_custom_catalog.json; normalize to {"servers": {...}}."""
    path = ensure_custom_mcp_catalog()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = _default_catalog()
        save_custom_mcp_catalog(raw)
        return raw

    if not isinstance(raw, dict):
        raw = _default_catalog()
    servers = raw.get("servers")
    if not isinstance(servers, dict):
        servers = {}
        raw["servers"] = servers

    changed = False
    cleaned: dict[str, Any] = {}
    for name, entry in servers.items():
        key = str(name).strip().casefold()
        if not key:
            continue
        if not isinstance(entry, dict):
            changed = True
            continue
        cleaned[key] = dict(entry)
        if key != str(name).strip():
            changed = True
    if cleaned != servers:
        changed = True
    raw["servers"] = cleaned
    if changed:
        save_custom_mcp_catalog(raw)
    return raw


def save_custom_mcp_catalog(config: dict[str, Any]) -> None:
    path = custom_mcp_catalog_path()
    DEVICE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def custom_catalog_server_names() -> list[str]:
    return sorted(load_custom_mcp_catalog().get("servers", {}).keys())


def get_custom_catalog_entry(name: str) -> dict[str, Any] | None:
    """Return a copy of the custom catalog entry, or None if unknown."""
    key = name.strip().casefold()
    entry = load_custom_mcp_catalog().get("servers", {}).get(key)
    if not isinstance(entry, dict):
        return None
    return dict(entry)


def upsert_custom_catalog_entry(name: str, entry: dict[str, Any]) -> None:
    """Create or replace a custom catalog recipe.

    Raises ValueError if name is empty, curated, or entry is missing required fields.
    """
    key = name.strip().casefold()
    if not key:
        raise ValueError("Custom MCP server name must be non-empty")
    if key in known_server_names():
        raise ValueError(
            f"{key!r} is a curated MCP server — use catalog.py / mcp.json, "
            "not mcp_custom_catalog.json."
        )
    if not isinstance(entry, dict):
        raise ValueError("Catalog entry must be a dict")

    transport = str(entry.get("transport") or "stdio").strip().casefold()
    if transport != "stdio":
        raise ValueError(
            f"Custom MCP servers only support transport 'stdio' for now "
            f"(got {transport!r})"
        )
    command = entry.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError(f"Custom server {key!r} needs a non-empty string 'command'")

    args = entry.get("args", [])
    if args is None:
        args = []
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ValueError(f"Custom server {key!r} 'args' must be a list of strings")

    stored = dict(entry)
    stored["transport"] = "stdio"
    stored["command"] = command.strip()
    stored["args"] = list(args)

    catalog = load_custom_mcp_catalog()
    servers = catalog.setdefault("servers", {})
    servers[key] = stored
    save_custom_mcp_catalog(catalog)


def remove_custom_catalog_entry(name: str) -> bool:
    """Remove a catalog entry. Returns True if it existed."""
    key = name.strip().casefold()
    catalog = load_custom_mcp_catalog()
    servers = catalog.setdefault("servers", {})
    if key not in servers:
        return False
    del servers[key]
    save_custom_mcp_catalog(catalog)
    return True


def connection_for_custom_server(name: str) -> dict[str, Any]:
    """Build a MultiServerMCPClient connection dict for a custom stdio server.

    Raises ValueError if unknown or misconfigured.
    """
    key = name.strip().casefold()
    entry = get_custom_catalog_entry(key)
    if entry is None:
        known = ", ".join(custom_catalog_server_names()) or "(none)"
        raise ValueError(
            f"Unknown custom MCP server {name!r}. Known custom: {known}"
        )

    transport = str(entry.get("transport") or "stdio").strip().casefold()
    if transport != "stdio":
        raise ValueError(
            f"Unsupported transport {transport!r} for custom MCP server {key!r}"
        )

    command = entry.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError(f"Custom MCP server {key!r} has no 'command'")

    args = entry.get("args") or []
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ValueError(f"Custom MCP server {key!r} has invalid 'args'")

    conn: dict[str, Any] = {
        "transport": "stdio",
        "command": command.strip(),
        "args": list(args),
    }

    cwd = entry.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        conn["cwd"] = cwd.strip()

    # Optional: map of env KEY -> value, or KEY -> "$OTHER_ENV" to pull from os.environ.
    raw_env = entry.get("env")
    if isinstance(raw_env, dict) and raw_env:
        resolved: dict[str, str] = {}
        for env_key, env_val in raw_env.items():
            if not isinstance(env_key, str) or not env_key.strip():
                continue
            if not isinstance(env_val, str):
                continue
            val = env_val
            if val.startswith("$") and len(val) > 1:
                ref = val[1:]
                val = (os.getenv(ref) or "").strip()
                if not val:
                    raise ValueError(
                        f"Custom MCP server {key!r} env {env_key!r} needs "
                        f"{ref} in the environment"
                    )
            resolved[env_key.strip()] = val
        if resolved:
            conn["env"] = resolved

    return conn
