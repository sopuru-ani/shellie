"""Skill discovery: scan dirs, parse SKILL.md frontmatter, build in-memory map.

Precedence (first match wins — scope-first, then client folder within scope):
  1. Project  .shellie/skills/
  2. Project  .claude/skills/
  3. Project  .agents/skills/
  4. Device   ~/.config/shellie/skills/
  5. Device   ~/.claude/skills/
  6. Device   ~/.agents/skills/
  7. Built-in (shellie package)

Project dirs only scanned when SKILLS_TRUST_PROJECT=1 is set in the environment.
"""

from __future__ import annotations

import importlib.resources
import os
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import yaml

from shellie.paths import DEVICE_CONFIG_DIR


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class SkillRecord(NamedTuple):
    name: str
    description: str
    location: Path          # absolute path to SKILL.md
    source: str             # human-readable label, e.g. "project:.shellie"

    @property
    def skill_dir(self) -> Path:
        return self.location.parent


@dataclass
class DiscoverResult:
    skills: dict[str, SkillRecord]          # name → winning record
    shadowed: list[tuple[str, str]]          # (name, source) shadowed by a winner
    failed: list[tuple[str, str]]            # (path, reason) for files with a name but bad body
    project_skipped: bool                   # True when project dirs were not scanned


# ---------------------------------------------------------------------------
# YAML frontmatter extraction
# ---------------------------------------------------------------------------

def _split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return (raw_yaml_block, body) or (None, full_text) if no frontmatter."""
    if not text.startswith("---"):
        return None, text
    first_nl = text.find("\n")
    if first_nl == -1:
        return None, text
    rest = text[first_nl + 1:]
    end = rest.find("\n---")
    if end == -1:
        return None, text
    raw = rest[:end]
    body = rest[end + 4:].lstrip("\n")  # skip past "\n---" and leading newline
    return raw, body


def _parse_frontmatter(path: Path) -> tuple[str | None, str | None, str]:
    """Return (name, description, body).

    Returns (None, None, "") when the file cannot be parsed or is missing
    required fields. description may still be None if YAML has no 'description'.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, None, str(exc)

    raw_yaml, body = _split_frontmatter(text)
    if raw_yaml is None:
        return None, None, "no YAML frontmatter found"

    # First try strict PyYAML; if it fails, retry with the common
    # "description: Use when: ..." colon-in-value footgun patched.
    data = None
    exc_msg = ""
    for attempt in (raw_yaml, _patch_bare_colon(raw_yaml)):
        try:
            data = yaml.safe_load(attempt)
            break
        except yaml.YAMLError as exc:
            exc_msg = str(exc)

    if not isinstance(data, dict):
        return None, None, f"YAML parse failed: {exc_msg}"

    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()

    if not name:
        return None, None, "missing 'name' field"
    if not description:
        return name, None, "missing 'description' field"

    # Cap description at spec maximum.
    if len(description) > 1024:
        description = description[:1021] + "…"

    return name, description, body


def _patch_bare_colon(raw_yaml: str) -> str:
    """Quote description values that contain an unquoted colon, e.g.
    description: Use when: the user asks...  →  description: "Use when: ..."
    """
    lines = raw_yaml.splitlines()
    out: list[str] = []
    in_desc_block = False
    for line in lines:
        if line.startswith("description:") and not in_desc_block:
            value = line[len("description:"):].strip()
            if value and not value.startswith(('"', "'", "|", ">")):
                # Escape inner quotes, then wrap.
                escaped = value.replace('"', '\\"')
                out.append(f'description: "{escaped}"')
                in_desc_block = False
                continue
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Directory scanning
# ---------------------------------------------------------------------------

def _skill_dirs(project_root: Path, *, trust_project: bool) -> list[tuple[Path, str]]:
    """Ordered list of (skills_dir, source_label) to scan, highest priority first."""
    dirs: list[tuple[Path, str]] = []

    if trust_project:
        dirs += [
            (project_root / ".shellie" / "skills", "project:.shellie"),
            (project_root / ".claude"  / "skills", "project:.claude"),
            (project_root / ".agents"  / "skills", "project:.agents"),
        ]

    dirs += [
        (DEVICE_CONFIG_DIR / "skills",                     "device:.shellie"),
        (Path.home() / ".claude"  / "skills",              "device:.claude"),
        (Path.home() / ".agents"  / "skills",              "device:.agents"),
    ]

    return dirs


def _builtin_skills_dir() -> Path | None:
    """Path to the shellie package's built-in skills directory."""
    try:
        # importlib.resources works both in editable installs and after pip install.
        pkg_ref = importlib.resources.files("shellie") / "skills" / "builtin"
        # Materialise as a concrete Path.
        with importlib.resources.as_file(pkg_ref) as p:
            return p if p.is_dir() else None
    except (TypeError, ModuleNotFoundError):
        return None


def _scan_dir(skills_dir: Path, source: str) -> list[tuple[SkillRecord, str | None]]:
    """Return list of (SkillRecord, error_or_None) for each skill subdirectory found."""
    results: list[tuple[SkillRecord, str | None]] = []
    if not skills_dir.is_dir():
        return results

    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in (".git", "node_modules", "__pycache__"):
            continue
        skill_md = entry / "SKILL.md"
        if not skill_md.is_file():
            continue

        name, description, body_or_err = _parse_frontmatter(skill_md)

        if name is None:
            # No usable name — silently skip.
            continue

        if description is None:
            # Has a name but is broken — report but don't add to map.
            results.append((
                SkillRecord(name=name, description="", location=skill_md, source=source),
                body_or_err or "missing description",
            ))
            continue

        results.append((
            SkillRecord(name=name, description=description, location=skill_md, source=source),
            None,
        ))

    return results


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def discover_skills(project_root: Path | None = None) -> DiscoverResult:
    """Scan all skill locations and return a precedence-resolved DiscoverResult."""
    from shellie.paths import find_project_root
    root = project_root or find_project_root()
    trust_project = os.getenv("SKILLS_TRUST_PROJECT", "").strip() in ("1", "true", "yes")

    skill_map: dict[str, SkillRecord] = {}
    shadowed: list[tuple[str, str]] = []
    failed: list[tuple[str, str]] = []

    scan_sources = _skill_dirs(root, trust_project=trust_project)

    # Scan external dirs in precedence order.
    for skills_dir, source in scan_sources:
        for record, error in _scan_dir(skills_dir, source):
            if error:
                failed.append((str(record.location), error))
                continue
            if record.name in skill_map:
                shadowed.append((record.name, source))
            else:
                skill_map[record.name] = record

    # Scan built-ins last (lowest priority).
    builtin_dir = _builtin_skills_dir()
    if builtin_dir:
        for record, error in _scan_dir(builtin_dir, "built-in"):
            if error:
                failed.append((str(record.location), error))
                continue
            if record.name in skill_map:
                shadowed.append((record.name, "built-in"))
            else:
                skill_map[record.name] = record

    return DiscoverResult(
        skills=skill_map,
        shadowed=shadowed,
        failed=failed,
        project_skipped=not trust_project,
    )


def skills_status_message(result: DiscoverResult) -> str:
    """One-line startup banner for skills, mirroring Cognee/MCP style."""
    parts: list[str] = []

    if result.project_skipped:
        parts.append("project untrusted (set SKILLS_TRUST_PROJECT=1)")

    count = len(result.skills)
    if count == 0:
        if not result.failed:
            parts.append("none found")
        else:
            parts.append("none loaded")
    else:
        names = ", ".join(sorted(result.skills))
        parts.append(f"{count} available: {names}")

    if result.failed:
        parts.append(f"{len(result.failed)} failed to load")

    return "; ".join(parts)
