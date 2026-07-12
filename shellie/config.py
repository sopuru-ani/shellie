"""Load environment from the user's project before agent or Cognee startup."""

import os
from pathlib import Path

from dotenv import dotenv_values

from shellie.paths import DEVICE_CONFIG_DIR, ensure_agent_dirs, find_project_root


def _apply_env_file(path: Path, into: dict[str, str | None]) -> None:
    if path.is_file():
        into.update(dotenv_values(path))


def load_project_env(project_root: Path | None = None) -> Path:
    """Load .env for the bound project.

    Precedence (highest wins): shell exports > project .env > device defaults.
    """
    root = (project_root or find_project_root()).resolve()
    merged: dict[str, str | None] = {}
    _apply_env_file(DEVICE_CONFIG_DIR / ".env", merged)
    _apply_env_file(root / ".env", merged)
    for key, value in merged.items():
        if value is not None and key not in os.environ:
            os.environ[key] = value
    return root


def bootstrap() -> Path:
    """Resolve project, load .env, create data dirs. Call before building the agent."""
    root = load_project_env()
    return ensure_agent_dirs(root)
