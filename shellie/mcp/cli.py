"""shellie-mcp — manage curated/custom MCP servers and the per-project client switch.

Curated:  ~/.config/shellie/mcp.json + catalog.py
Custom:   ~/.config/shellie/mcp_custom.json + mcp_custom_catalog.json
Project:  .env MCP_ENABLED=1 (whether this Shellie run loads them)
Secrets:  device/project .env or per-server .env — never the JSON toggle/catalog files
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import dotenv_values

from shellie.mcp.auth import ensure_pat_for_entry, upsert_project_env
from shellie.mcp.catalog import catalog_server_names, get_catalog_entry
from shellie.mcp.config import (
    custom_mcp_config_path,
    ensure_custom_mcp_config,
    ensure_mcp_config,
    is_custom_server_enabled,
    is_server_enabled,
    known_custom_server_names,
    mcp_config_path,
    set_custom_server_enabled,
    set_server_enabled,
)
from shellie.mcp.custom_catalog import (
    custom_catalog_server_names,
    custom_mcp_catalog_path,
    ensure_custom_mcp_catalog,
    get_custom_catalog_entry,
)
from shellie.mcp.mcp import mcp_enabled, mcp_status_message
from shellie.paths import DEVICE_CONFIG_DIR, find_project_root

_MCP_ENABLED_KEY = "MCP_ENABLED"


def _load_device_env() -> None:
    """Load ~/.config/shellie/.env into os.environ (do not override existing)."""
    path = DEVICE_CONFIG_DIR / ".env"
    if not path.is_file():
        return
    for key, value in dotenv_values(path).items():
        if value is not None and key not in os.environ:
            os.environ[key] = value


def _load_project_env() -> None:
    """Load cwd project's .env (do not override keys already set)."""
    root = find_project_root()
    path = root / ".env"
    if not path.is_file():
        return
    for key, value in dotenv_values(path).items():
        if value is not None and key not in os.environ:
            os.environ[key] = value


def _known_names_hint() -> str:
    curated = ", ".join(catalog_server_names()) or "(none)"
    custom = ", ".join(custom_catalog_server_names()) or "(none)"
    return f"Curated: {curated}. Custom catalog: {custom}."


def cmd_list(_args: argparse.Namespace) -> int:
    """Show curated + custom servers and enable / config state."""
    ensure_mcp_config()
    ensure_custom_mcp_config()
    ensure_custom_mcp_catalog()

    print(f"Curated config: {mcp_config_path()}")
    print(f"Custom toggles: {custom_mcp_config_path()}")
    print(f"Custom catalog: {custom_mcp_catalog_path()}")
    print()
    print("Curated:")
    for name in catalog_server_names():
        entry = get_catalog_entry(name) or {}
        enabled = is_server_enabled(name)
        token_env = entry.get("token_env")
        has_token = bool(token_env and (os.getenv(token_env) or "").strip())
        flag = "on " if enabled else "off"
        token_note = "token set" if has_token else f"missing {token_env}"
        desc = entry.get("description", "")
        print(f"  {name:12} [{flag}]  {token_note}")
        if desc:
            print(f"               {desc}")

    print()
    print("Custom:")
    custom_names = sorted(
        set(custom_catalog_server_names()) | set(known_custom_server_names())
    )
    if not custom_names:
        print("  (none — register in mcp_custom_catalog.json, then enable)")
        return 0

    for name in custom_names:
        entry = get_custom_catalog_entry(name) or {}
        enabled = is_custom_server_enabled(name)
        flag = "on " if enabled else "off"
        if not entry:
            note = "no catalog entry"
        else:
            command = entry.get("command") or "?"
            note = f"stdio → {command}"
        desc = entry.get("description", "")
        print(f"  {name:12} [{flag}]  {note}")
        if desc:
            print(f"               {desc}")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    """One-shot status (same ideas as the Shellie REPL banner)."""
    project = find_project_root()
    print(f"Project (cwd): {project}")
    print(f"Device config: {DEVICE_CONFIG_DIR}")
    print(f"MCP:           {mcp_status_message()}")
    print(f"MCP_ENABLED:   {'yes' if mcp_enabled() else 'no'}")
    custom_on = [
        n for n in known_custom_server_names() if is_custom_server_enabled(n)
    ]
    if custom_on:
        print(f"Custom on:     {', '.join(custom_on)}")
    return 0


def cmd_enable(args: argparse.Namespace) -> int:
    """Enable a curated or custom server (device toggles)."""
    name = args.name.strip().casefold()

    # Curated first (PAT flow)
    entry = get_catalog_entry(name)
    if entry is not None:
        auth = (entry.get("auth") or "pat").strip().casefold()
        if entry.get("token_env"):
            if auth == "pat":
                err = ensure_pat_for_entry(entry)
                if err:
                    print(err, file=sys.stderr)
                    return 1
            else:
                print(
                    f"Unsupported auth {auth!r} for {name!r} (only 'pat' for now).",
                    file=sys.stderr,
                )
                return 1
        try:
            set_server_enabled(name, True)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Enabled curated {name} in {mcp_config_path()}")
        print("Tip: turn the client on for this project with: shellie-mcp on")
        return 0

    # Custom: must already be in mcp_custom_catalog.json
    custom_entry = get_custom_catalog_entry(name)
    if custom_entry is None:
        print(
            f"Unknown MCP server {args.name!r}. {_known_names_hint()}",
            file=sys.stderr,
        )
        return 1

    try:
        set_custom_server_enabled(name, True)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Enabled custom {name} in {custom_mcp_config_path()}")
    print("Tip: turn the client on for this project with: shellie-mcp on")
    print("Restart shellie so custom tools load.")
    return 0


def cmd_disable(args: argparse.Namespace) -> int:
    """Disable a curated or custom server (does not delete tokens / catalog)."""
    name = args.name.strip().casefold()

    if get_catalog_entry(name) is not None:
        try:
            set_server_enabled(name, False)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Disabled curated {name} in {mcp_config_path()}")
        print("(Token left in .env if present — only the server toggle changed.)")
        return 0

    if (
        get_custom_catalog_entry(name) is not None
        or name in known_custom_server_names()
    ):
        try:
            set_custom_server_enabled(name, False)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Disabled custom {name} in {custom_mcp_config_path()}")
        print("(Catalog entry left in place — only the toggle changed.)")
        return 0

    print(
        f"Unknown MCP server {args.name!r}. {_known_names_hint()}",
        file=sys.stderr,
    )
    return 1


def cmd_on(_args: argparse.Namespace) -> int:
    """Set MCP_ENABLED=1 in the project .env (cwd / git root)."""
    root = find_project_root()
    path = upsert_project_env(root, _MCP_ENABLED_KEY, "1")
    print(f"MCP client on for project {root}")
    print(f"Wrote {_MCP_ENABLED_KEY}=1 to {path}")
    print("Restart shellie (or start a new session) so the agent reloads tools.")
    return 0


def cmd_off(_args: argparse.Namespace) -> int:
    """Set MCP_ENABLED=0 in the project .env (cwd / git root)."""
    root = find_project_root()
    path = upsert_project_env(root, _MCP_ENABLED_KEY, "0")
    print(f"MCP client off for project {root}")
    print(f"Wrote {_MCP_ENABLED_KEY}=0 to {path}")
    print("Restart shellie (or start a new session) so the agent drops MCP tools.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shellie-mcp",
        description="Manage Shellie MCP servers (device) and client switch (project).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser(
        "list", help="List curated and custom MCP servers and enable state"
    )
    p_list.set_defaults(func=cmd_list)

    p_status = sub.add_parser("status", help="Show MCP client / config status")
    p_status.set_defaults(func=cmd_status)

    p_enable = sub.add_parser(
        "enable", help="Enable a curated or custom MCP server (device)"
    )
    p_enable.add_argument("name", help="Server id (e.g. github, weather)")
    p_enable.set_defaults(func=cmd_enable)

    p_disable = sub.add_parser(
        "disable", help="Disable a curated or custom MCP server (device)"
    )
    p_disable.add_argument("name", help="Server id (e.g. github, weather)")
    p_disable.set_defaults(func=cmd_disable)

    p_on = sub.add_parser("on", help="Turn MCP client on for this project (.env)")
    p_on.set_defaults(func=cmd_on)

    p_off = sub.add_parser("off", help="Turn MCP client off for this project (.env)")
    p_off.set_defaults(func=cmd_off)

    return parser


def main(argv: list[str] | None = None) -> None:
    _load_device_env()
    _load_project_env()
    parser = build_parser()
    args = parser.parse_args(argv)
    code = args.func(args)
    sys.exit(code if isinstance(code, int) else 0)


if __name__ == "__main__":
    main()
