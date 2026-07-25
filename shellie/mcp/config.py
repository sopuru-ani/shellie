"""Device-level MCP server toggles.

Curated:  ~/.config/shellie/mcp.json
  - Which built-in catalog servers (e.g. github) are enabled.
  - Connection recipes live in catalog.py (code).

Custom:   ~/.config/shellie/mcp_custom.json
  - Enable flags for user/agent-defined servers only.
  - Connection recipes live in mcp_custom_catalog.json (next file).

Secrets stay in device/project .env — never in these JSON files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shellie.paths import DEVICE_CONFIG_DIR

# Curated server ids Shellie knows about. Values are per-server flags only.
_DEFAULT_SERVERS: dict[str, dict[str, Any]] = {
    "github": {"enabled": False},
}


def mcp_config_path() -> Path:
    return DEVICE_CONFIG_DIR / "mcp.json"


def custom_mcp_config_path() -> Path:
    return DEVICE_CONFIG_DIR / "mcp_custom.json"


def _default_config() -> dict[str, Any]:
    return {"servers": {name: dict(flags) for name, flags in _DEFAULT_SERVERS.items()}}


def _default_custom_config() -> dict[str, Any]:
    return {"servers": {}}


def ensure_mcp_config() -> Path:
    """Create device mcp.json with defaults if missing. Returns the config path."""
    DEVICE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = mcp_config_path()
    if not path.is_file():
        save_mcp_config(_default_config())
    return path


def ensure_custom_mcp_config() -> Path:
    """Create device mcp_custom.json with empty servers if missing."""
    DEVICE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = custom_mcp_config_path()
    if not path.is_file():
        save_custom_mcp_config(_default_custom_config())
    return path


def load_mcp_config() -> dict[str, Any]:
    """Load mcp.json, merging in any new curated servers missing from an older file."""
    path = ensure_mcp_config()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = _default_config()
        save_mcp_config(raw)
        return raw

    if not isinstance(raw, dict):
        raw = _default_config()
    servers = raw.get("servers")
    if not isinstance(servers, dict):
        servers = {}
        raw["servers"] = servers

    changed = False
    for name, defaults in _DEFAULT_SERVERS.items():
        if name not in servers or not isinstance(servers[name], dict):
            servers[name] = dict(defaults)
            changed = True
        else:
            # Keep unknown keys; ensure "enabled" exists.
            if "enabled" not in servers[name]:
                servers[name]["enabled"] = bool(defaults.get("enabled", False))
                changed = True
    if changed:
        save_mcp_config(raw)
    return raw


def load_custom_mcp_config() -> dict[str, Any]:
    """Load mcp_custom.json; normalize to {"servers": {...}}."""
    path = ensure_custom_mcp_config()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = _default_custom_config()
        save_custom_mcp_config(raw)
        return raw

    if not isinstance(raw, dict):
        raw = _default_custom_config()
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
            cleaned[key] = {"enabled": False}
            changed = True
            continue
        if "enabled" not in entry:
            entry = dict(entry)
            entry["enabled"] = False
            changed = True
        cleaned[key] = entry
    if cleaned != servers:
        changed = True
    raw["servers"] = cleaned
    if changed:
        save_custom_mcp_config(raw)
    return raw


def save_mcp_config(config: dict[str, Any]) -> None:
    path = mcp_config_path()
    DEVICE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def save_custom_mcp_config(config: dict[str, Any]) -> None:
    path = custom_mcp_config_path()
    DEVICE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def known_server_names() -> list[str]:
    return sorted(_DEFAULT_SERVERS.keys())


def known_custom_server_names() -> list[str]:
    """Names present in mcp_custom.json (any enable state)."""
    servers = load_custom_mcp_config().get("servers", {})
    return sorted(servers.keys())


def is_server_enabled(name: str) -> bool:
    name = name.strip().casefold()
    servers = load_mcp_config().get("servers", {})
    entry = servers.get(name)
    if not isinstance(entry, dict):
        return False
    return bool(entry.get("enabled"))


def is_custom_server_enabled(name: str) -> bool:
    name = name.strip().casefold()
    servers = load_custom_mcp_config().get("servers", {})
    entry = servers.get(name)
    if not isinstance(entry, dict):
        return False
    return bool(entry.get("enabled"))


def set_server_enabled(name: str, enabled: bool) -> None:
    """Enable or disable a curated server. Raises ValueError if name is unknown."""
    name = name.strip().casefold()
    if name not in _DEFAULT_SERVERS:
        known = ", ".join(known_server_names())
        raise ValueError(f"Unknown MCP server {name!r}. Known: {known}")
    config = load_mcp_config()
    servers = config.setdefault("servers", {})
    entry = servers.setdefault(name, dict(_DEFAULT_SERVERS[name]))
    entry["enabled"] = bool(enabled)
    save_mcp_config(config)


def set_custom_server_enabled(name: str, enabled: bool) -> None:
    """Enable or disable a custom server toggle (creates the entry if missing).

    Does not validate catalog/connection — that lives in mcp_custom_catalog.json.
    Raises ValueError if name collides with a curated server id.
    """
    name = name.strip().casefold()
    if not name:
        raise ValueError("Custom MCP server name must be non-empty")
    if name in _DEFAULT_SERVERS:
        raise ValueError(
            f"{name!r} is a curated MCP server — use set_server_enabled / "
            f"shellie-mcp enable|disable, not the custom toggle file."
        )
    config = load_custom_mcp_config()
    servers = config.setdefault("servers", {})
    entry = servers.setdefault(name, {})
    if not isinstance(entry, dict):
        entry = {}
        servers[name] = entry
    entry["enabled"] = bool(enabled)
    save_custom_mcp_config(config)


def enabled_server_names() -> list[str]:
    """Curated servers marked enabled in mcp.json (order: known_server_names)."""
    return [name for name in known_server_names() if is_server_enabled(name)]


def enabled_custom_server_names() -> list[str]:
    """Custom servers marked enabled in mcp_custom.json."""
    return [
        name
        for name in known_custom_server_names()
        if is_custom_server_enabled(name)
    ]
