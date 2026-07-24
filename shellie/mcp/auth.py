"""Credential helpers for shellie-mcp enable (catalog-driven).

PAT path today; other auth kinds can branch here later without growing cli.py.
"""

from __future__ import annotations

import getpass
import os
import re
from pathlib import Path
from typing import Any

import httpx

from shellie.paths import DEVICE_CONFIG_DIR

_ENV_KEY_RE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=")


def device_env_path() -> Path:
    return DEVICE_CONFIG_DIR / ".env"


def upsert_env_file(path: Path, key: str, value: str) -> Path:
    """Create or update KEY=value in an .env file; set os.environ too."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()

    # Key update set to false initially then true when key is found and updated
    updated = False
    out: list[str] = []
    for line in lines:
        match = _ENV_KEY_RE.match(line)
        if match and match.group(1) == key:
            out.append(f"{key}={value}")
            updated = True
        else:
            out.append(line)
    if not updated:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")

    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.environ[key] = value
    return path


def upsert_device_env(key: str, value: str) -> Path:
    """Create or update KEY=value in ~/.config/shellie/.env; set os.environ too."""
    return upsert_env_file(device_env_path(), key, value)


def upsert_project_env(project_root: Path, key: str, value: str) -> Path:
    """Create or update KEY=value in <project>/.env; set os.environ too."""
    return upsert_env_file(project_root / ".env", key, value)


def validate_pat(token: str, *, validate_url: str) -> tuple[bool, str]:
    """GET validate_url with Bearer token. Returns (ok, message)."""
    try:
        response = httpx.get(
            validate_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "shellie-mcp",
            },
            timeout=15.0,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        return False, f"network error: {exc}"

    if response.status_code == 200:
        login = "?"
        try:
            login = str(response.json().get("login") or "?")
        except Exception:
            pass
        return True, f"authenticated as {login}"

    if response.status_code == 401:
        return False, "invalid or expired token (HTTP 401)"

    body = (response.text or "").strip().replace("\n", " ")[:160]
    return False, f"unexpected HTTP {response.status_code}: {body}"


def ensure_pat_for_entry(entry: dict[str, Any]) -> str | None:
    """If token_env is unset, prompt / validate / save. Return error string or None."""
    token_env = entry.get("token_env")
    if not token_env:
        return None

    existing = (os.getenv(token_env) or "").strip()
    if existing:
        return None

    create_url = entry.get("pat_create_url") or ""
    hint = entry.get("pat_hint") or ""
    validate_url = entry.get("validate_url")
    if not validate_url:
        return f"catalog entry missing validate_url for {token_env}"

    print(f"To enable this MCP server you need a token ({token_env}).")
    if create_url:
        print(f"Get one at: {create_url}")
    if hint:
        print(hint)
    print()

    try:
        token = getpass.getpass("Paste token (input hidden): ").strip()
    except (EOFError, KeyboardInterrupt):
        return "cancelled — no token entered"

    if not token:
        return "empty token — not enabled"

    print("Checking token...")
    ok, message = validate_pat(token, validate_url=validate_url)
    if not ok:
        return f"token check failed: {message}"

    path = upsert_device_env(token_env, token)
    print(f"Saved {token_env} to {path} ({message})")
    return None
