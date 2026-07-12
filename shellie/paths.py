"""Project and device path resolution for session and Cognee memory."""

from pathlib import Path

DEVICE_CONFIG_DIR = Path.home() / ".config" / "shellie"


def find_project_root(start: Path | None = None) -> Path:
    """Git repo root if inside one, otherwise the directory where the agent was launched."""
    start = (start or Path.cwd()).resolve()
    current = start
    while True:
        if (current / ".git").is_dir():
            return current
        parent = current.parent
        if parent == current or parent == Path.home().resolve():
            return start
        current = parent


def project_agent_dir(project_root: Path | None = None) -> Path:
    return (project_root or find_project_root()) / ".agent"


def project_session_db(project_root: Path | None = None) -> Path:
    return project_agent_dir(project_root) / "session.sqlite"


def project_cognee_dir(project_root: Path | None = None) -> Path:
    return project_agent_dir(project_root) / "cognee"


def device_cognee_dir() -> Path:
    return DEVICE_CONFIG_DIR / "cognee"


def ensure_agent_dirs(project_root: Path | None = None) -> Path:
    """Create .agent/ in the project and device config dirs; return project root."""
    root = project_root or find_project_root()
    project_agent_dir(root).mkdir(parents=True, exist_ok=True)
    project_cognee_dir(root).mkdir(parents=True, exist_ok=True)
    DEVICE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    device_cognee_dir().mkdir(parents=True, exist_ok=True)
    return root
