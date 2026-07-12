"""Cognee long-term memory for project and device tiers."""

from __future__ import annotations

import asyncio
import os
from contextlib import contextmanager
from pathlib import Path

from shellie.paths import device_cognee_dir, project_cognee_dir

PROJECT_DATASET = "project"
DEVICE_DATASET = "device"

_project_root: Path | None = None
_cognee_available: bool | None = None


def _env_truthy(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def cognee_available() -> bool:
    """Whether the cognee package is installed."""
    global _cognee_available
    if _cognee_available is None:
        try:
            import cognee  # noqa: F401
        except ImportError:
            _cognee_available = False
        else:
            _cognee_available = True
    return _cognee_available


def cognee_memory_enabled() -> bool:
    """Installed, explicitly enabled, and configured for this project."""
    if not cognee_available():
        return False

    if os.getenv("COGNEE_ENABLED") is not None:
        return _env_truthy("COGNEE_ENABLED", default=False)

    # Backward compatible: enable when Cognee config is present in project .env
    return bool(os.getenv("COGNEE_LLM_MODEL") or os.getenv("COGNEE_EMBEDDING_MODEL"))


def cognee_status_message() -> str:
    if not cognee_available():
        return (
            "not installed — install with: pip install 'shellie[cognee]' "
            "or: pipx inject shellie cognee"
        )
    if not cognee_memory_enabled():
        if os.getenv("COGNEE_ENABLED") is not None and not _env_truthy(
            "COGNEE_ENABLED", default=False
        ):
            return "disabled (COGNEE_ENABLED=0 in .env)"
        return "disabled — set COGNEE_ENABLED=1 and COGNEE_* vars in .env"
    return "ready (remember/recall tools enabled)"


def init_cognee_memory(project_root: Path) -> None:
    """Bind Cognee tools to the current project root."""
    global _project_root
    _project_root = project_root.resolve()
    if not cognee_memory_enabled():
        return
    project_cognee_dir(_project_root).mkdir(parents=True, exist_ok=True)
    device_cognee_dir().mkdir(parents=True, exist_ok=True)


def _require_project_root() -> Path:
    if _project_root is None:
        raise RuntimeError("Cognee memory is not initialized")
    return _project_root


def _disabled_message() -> str:
    if not cognee_available():
        return (
            "Cognee is not installed. Install with: pip install 'shellie[cognee]' "
            "or: pipx inject shellie cognee — then restart shellie."
        )
    return (
        "Cognee memory is disabled for this project. "
        "Set COGNEE_ENABLED=1 and COGNEE_* vars in .env, then restart shellie."
    )


def _apply_cognee_config() -> None:
    """Apply COGNEE_* env vars so Cognee does not share chat LLM settings."""
    import cognee

    llm_config: dict[str, str] = {}
    for env_key, config_key in (
        ("COGNEE_LLM_PROVIDER", "llm_provider"),
        ("COGNEE_LLM_MODEL", "llm_model"),
        ("COGNEE_LLM_API_KEY", "llm_api_key"),
        ("COGNEE_LLM_ENDPOINT", "llm_endpoint"),
    ):
        value = os.getenv(env_key)
        if value:
            llm_config[config_key] = value
    if llm_config:
        cognee.config.set_llm_config(llm_config)

    embedding_config: dict[str, str | int] = {}
    for env_key, config_key in (
        ("COGNEE_EMBEDDING_PROVIDER", "embedding_provider"),
        ("COGNEE_EMBEDDING_MODEL", "embedding_model"),
        ("COGNEE_EMBEDDING_API_KEY", "embedding_api_key"),
        ("COGNEE_EMBEDDING_ENDPOINT", "embedding_endpoint"),
    ):
        value = os.getenv(env_key)
        if value:
            embedding_config[config_key] = value
    dimensions = os.getenv("COGNEE_EMBEDDING_DIMENSIONS")
    if dimensions:
        embedding_config["embedding_dimensions"] = int(dimensions)
    if embedding_config:
        cognee.config.set_embedding_config(embedding_config)


@contextmanager
def _cognee_tier(tier_dir: Path):
    import cognee

    tier_dir.mkdir(parents=True, exist_ok=True)
    system_dir = tier_dir / "system"
    data_dir = tier_dir / "data"
    system_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    cognee.config.system_root_directory(str(system_dir.resolve()))
    cognee.config.data_root_directory(str(data_dir.resolve()))
    _apply_cognee_config()
    yield


def _format_recall_results(results) -> str:
    if not results:
        return "No matching memories found."

    lines: list[str] = []
    for index, item in enumerate(results[:10], 1):
        text = getattr(item, "text", None) or str(item)
        text = text.strip()
        if text:
            lines.append(f"{index}. {text}")
    return "\n".join(lines) if lines else "No matching memories found."


async def _remember(tier_dir: Path, dataset: str, text: str) -> str:
    import cognee

    fact = text.strip()
    if not fact:
        return "Nothing to remember (empty text)."

    with _cognee_tier(tier_dir):
        result = await cognee.remember(
            fact,
            dataset_name=dataset,
            self_improvement=False,
        )

    status = getattr(result, "status", "stored")
    return f"Saved to {dataset} memory ({status})."


async def _recall(tier_dir: Path, dataset: str, query: str) -> str:
    import cognee

    query_text = query.strip()
    if not query_text:
        return "Recall query is empty."

    with _cognee_tier(tier_dir):
        results = await cognee.recall(
            query_text,
            datasets=[dataset],
            top_k=8,
        )

    return _format_recall_results(results)


def remember_project(text: str) -> str:
    if not cognee_memory_enabled():
        return _disabled_message()
    root = _require_project_root()
    return asyncio.run(_remember(project_cognee_dir(root), PROJECT_DATASET, text))


def remember_device(text: str) -> str:
    if not cognee_memory_enabled():
        return _disabled_message()
    _require_project_root()
    return asyncio.run(_remember(device_cognee_dir(), DEVICE_DATASET, text))


def recall_project(query: str) -> str:
    if not cognee_memory_enabled():
        return _disabled_message()
    root = _require_project_root()
    return asyncio.run(_recall(project_cognee_dir(root), PROJECT_DATASET, query))


def recall_device(query: str) -> str:
    if not cognee_memory_enabled():
        return _disabled_message()
    _require_project_root()
    return asyncio.run(_recall(device_cognee_dir(), DEVICE_DATASET, query))
