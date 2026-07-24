# shellie

A local CLI assistant for system tasks, codebase work, and light research. **Install once, `cd` into any project, drop a `.env` there** — the agent binds to that project automatically.

Requires **Python 3.10+**.

---

## Installation (recommended — pipx)

[pipx](https://pipx.pypa.io/stable/) installs `shellie` as a global CLI command. No virtualenv activation in every new terminal.

### 1. Install pipx

**Linux (Fedora)**

```bash
sudo dnf install pipx
pipx ensurepath
```

**Linux (Ubuntu / Debian 23.04+)**

```bash
sudo apt update
sudo apt install pipx
pipx ensurepath
```

**macOS**

```bash
brew install pipx
pipx ensurepath
```

**Windows (PowerShell)**

```powershell
# Option A — Scoop (recommended)
scoop install pipx
pipx ensurepath

# Option B — pip
py -m pip install --user pipx
pipx ensurepath
```

Close and reopen your terminal after `pipx ensurepath` so `shellie` is on your PATH.

### 2. Install shellie (once per machine)

Run this **once** from any directory — pipx manages its own install location (you do not need a special folder for the tool itself):

```bash
# Base install (chat + session memory only — no Cognee / MCP extras)
pipx install git+https://github.com/sopuru-ani/shellie.git

# With Cognee long-term memory (heavier install)
pipx install "shellie[cognee] @ git+https://github.com/sopuru-ani/shellie.git"

# With MCP client (GitHub tools, etc.)
pipx install "shellie[mcp] @ git+https://github.com/sopuru-ani/shellie.git"

# Both extras
pipx install "shellie[cognee,mcp] @ git+https://github.com/sopuru-ani/shellie.git"
```

Base install is quick. The `[cognee]` extra adds Cognee and may take several minutes. The `[mcp]` extra adds `langchain-mcp-adapters` (and registers the `shellie-mcp` CLI).

**Add Cognee later** (if you installed without it):

```bash
pipx inject shellie cognee
```

**Add MCP later:**

```bash
pipx inject shellie langchain-mcp-adapters
# or: pip install 'shellie[mcp]'
```

**Optional YAML linting** (for `read_lint` on `.yml` / `.yaml`):

```bash
pipx inject shellie yamllint
# or: pip install 'shellie[lint]'
```

After any `pipx inject`, quit Shellie (`/bye`) and start it again in a **new terminal** so the updated environment is picked up.

Verify:

```bash
shellie
```

Type `/bye` to quit.

### 3. Use it in any project

Each project gets its own `.env` and `.shellie/` data. The install step above is **not** repeated per project.

```bash
cd ~/Code/my-new-app          # Windows: cd C:\Users\You\Code\my-new-app
```

Copy the env template from the repo (or download [`.env.example`](.env.example) from GitHub), then edit your API keys:

```bash
# Linux / macOS
curl -o .env https://raw.githubusercontent.com/sopuru-ani/shellie/main/.env.example
# or copy manually from a cloned repo

# Windows (PowerShell)
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/sopuru-ani/shellie/main/.env.example" -OutFile .env
```

Edit `.env`, then run:

```bash
cd ~/Code/my-new-app
shellie
```

Startup should show your project path and config file:

```
Project root:  /home/you/Code/my-new-app
Config:        /home/you/Code/my-new-app/.env
```

**Important:** `shellie` is on PATH everywhere, but you should **`cd` into the project you are working on** before running it so it loads that project's `.env` and memory.

### Updating after a git push

Match the update command to how you installed:

```bash
# Base install (no Cognee / MCP extras)
pipx reinstall shellie
# or: pipx install --force git+https://github.com/sopuru-ani/shellie.git

# Installed with extras — reinstall with the same extras
pipx install --force "shellie[cognee,mcp] @ git+https://github.com/sopuru-ani/shellie.git"

# Base install + inject — reinstall keeps injects; after a plain --force install, re-inject:
pipx inject shellie cognee
pipx inject shellie langchain-mcp-adapters
```

---

## Installation (alternative — clone + editable install)

Use this if you are **developing** the agent itself or prefer a local venv over pipx.

```bash
git clone https://github.com/sopuru-ani/shellie.git
cd shellie
python -m venv venv
```

Activate the venv:

```bash
# Linux / macOS
source venv/bin/activate

# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
```

Install (pick one):

```bash
pip install -e .                    # base — no Cognee / MCP
pip install -e ".[cognee]"          # with Cognee memory
pip install -e ".[mcp]"             # with MCP client + shellie-mcp
pip install -e ".[cognee,mcp]"      # both
```

Each new terminal session (unless you use pipx or an alias):

```bash
source /path/to/shellie/venv/bin/activate   # or Windows Activate.ps1
cd /path/to/your-project
shellie
```

**Optional alias** (skip `activate`):

```bash
# Linux / macOS — add to ~/.zshrc or ~/.bashrc
alias shellie='/path/to/shellie/venv/bin/shellie'
```

---

## Per-project configuration

Put `.env` in the **project root** where you run `shellie` (git root or launch directory). The package install directory is never used for secrets.

Optional device-wide defaults: `~/.config/shellie/.env` on Linux/macOS (overridden by the project `.env`).

Add `.shellie/` to each project's `.gitignore` — it holds session and Cognee project memory.

### Optional Cognee (two layers)

| Layer | Control | Effect |
|-------|---------|--------|
| **Install** | `shellie` vs `shellie[cognee]` (or `pipx inject`) | Whether the Cognee package is on the machine |
| **Runtime** | `COGNEE_ENABLED=1` or `0` in **project** `.env` | Whether this project uses remember/recall (no reinstall) |

**Chat + session SQLite always work** with only `LLM_*` in `.env`.

**Enable Cognee for a project:**

```dotenv
COGNEE_ENABLED=1
# plus COGNEE_LLM_* and COGNEE_EMBEDDING_* — see Configuration below
```

**Disable Cognee for a project** (package can stay installed):

```dotenv
COGNEE_ENABLED=0
```

Restart `shellie` after changing `.env`. Startup shows e.g. `Cognee: ready` or `Cognee: disabled (COGNEE_ENABLED=0 in .env)`.

If `COGNEE_ENABLED` is omitted but `COGNEE_LLM_MODEL` or `COGNEE_EMBEDDING_MODEL` is set, Cognee is enabled automatically (backward compatible).

### Optional MCP (device servers + per-project switch)

MCP adds external tools (starting with **GitHub**) via curated remote servers. Config is split like Cognee:

| Layer | Where | Effect |
|-------|--------|--------|
| **Install** | `shellie[mcp]` or `pipx inject shellie langchain-mcp-adapters` | Adapters + `shellie-mcp` CLI on the machine |
| **Servers** | `~/.config/shellie/mcp.json` (via `shellie-mcp enable` / `disable`) | Which curated servers are on this device |
| **Secrets** | Prefer `~/.config/shellie/.env` (PAT saved by `shellie-mcp enable`) | Tokens — never stored in `mcp.json` |
| **Runtime** | `MCP_ENABLED=1` in **project** `.env` (`shellie-mcp on` / `off`) | Whether this project loads MCP tools |

**One-time device setup (GitHub):**

```bash
shellie-mcp enable github   # prompts for PAT if missing; validates; saves to device .env
shellie-mcp list
```

**Per project** (from that project's directory):

```bash
cd ~/Code/my-app
shellie-mcp on              # writes MCP_ENABLED=1 to this project's .env
shellie                     # banner should show MCP connected / tools loaded
```

Turn the client off without uninstalling or disabling the device server:

```bash
shellie-mcp off             # MCP_ENABLED=0
```

Useful commands: `shellie-mcp status`, `shellie-mcp list`, `shellie-mcp enable|disable <name>`, `shellie-mcp on|off`. Restart `shellie` after changing enablement so tools reload.

---

## REPL commands

| Command | Description |
|---------|-------------|
| `/shell` | Interactive subshell (`/chat` to return) |
| `/shell <cmd>` | Run one command in a fresh subshell |
| `/clear` | Wipe this project's chat session |
| `/bye` | Exit |

Chat input at `~>` does **not** run shell commands — the agent must call `terminal_run`, or you use `/shell`.

Set `AGENT_DEBUG=1` in your project `.env` for raw LangChain logs.

---

## Memory

Three tiers, keyed automatically from the directory you launch in:

| Tier | Storage | Purpose |
|------|---------|---------|
| **Session** | `.shellie/session.sqlite` | Full chat history for this project |
| **Project (Cognee)** | `.shellie/cognee/` | Durable facts about this repo |
| **Device (Cognee)** | `~/.config/shellie/cognee/` | Machine-wide facts (OS, tools, preferences) |

- One session per project folder; survives restart until `/clear`.
- Cognee tools: `remember_project`, `remember_device`, `recall_project`, `recall_device`.

### Testing Cognee

On startup, look for `Cognee: ready`. Then try:

```
remember that this machine uses Fedora and dnf
```

Quit with `/bye`, restart, and ask about your package manager. If it recalls the fact, device memory is working.

---

## Tools

| Tool | Use |
|------|-----|
| `terminal_run` | Non-interactive shell commands (persistent shell, venv stripped from PATH) |
| `file_read` / `file_write` | Read or overwrite whole project files |
| `file_edit` | Exact search-and-replace patch in an existing file |
| `file_grep` | Search file contents (pattern + optional path/glob) |
| `search` / `wikipedia` / `web_fetch` | External lookup when needed |
| `remember_*` / `recall_*` | Long-term Cognee memory |
| `github_*` (etc.) | MCP tools when `shellie[mcp]` is installed, a server is enabled, and `MCP_ENABLED=1` |

Interactive commands (`gh auth login`, `ssh`, editors, REPLs) are blocked — use `/shell` instead. Sensitive commands (`git push`, `rm`, `sudo`, package installs) require typing `yes` at a prompt.

---

## Configuration (`.env`)

Copy [`.env.example`](.env.example) into **your project root** and fill in API keys.

**Minimum for chat + session** — only `LLM_*` is required.

**Cognee** — set `COGNEE_ENABLED=1` and the `COGNEE_*` block below when you want long-term memory. Chat and Cognee use separate LLM settings.

**MCP** — set `MCP_ENABLED=1` (or run `shellie-mcp on`) after installing `shellie[mcp]` and enabling a server with `shellie-mcp enable github`. Prefer putting `GITHUB_PERSONAL_ACCESS_TOKEN` in the device `.env` (`~/.config/shellie/.env`).

**Chat agent** (`LLM_*`) — LangChain; `LLM_PROVIDER` selects the client
(`openai` default, or `anthropic` / `google`):

```dotenv
LLM_PROVIDER=openai
LLM_MODEL="nvidia/your-model-id"
LLM_ENDPOINT="https://integrate.api.nvidia.com/v1"
LLM_API_KEY="nvapi-..."
```

For Anthropic or Google, set `LLM_PROVIDER` and the matching model/key; leave
`LLM_ENDPOINT` unset unless you use a custom proxy. See `.env.example`.

**Cognee** (`COGNEE_LLM_*`, `COGNEE_EMBEDDING_*`) — remember/recall only:

```dotenv
COGNEE_LLM_PROVIDER="custom"
COGNEE_LLM_MODEL="hosted_vllm/nvidia/your-model-id"
COGNEE_LLM_ENDPOINT="https://integrate.api.nvidia.com/v1"
COGNEE_LLM_API_KEY="nvapi-..."

COGNEE_EMBEDDING_PROVIDER="openai_compatible"
COGNEE_EMBEDDING_MODEL="nvidia/nv-embed-v1"
COGNEE_EMBEDDING_ENDPOINT="https://integrate.api.nvidia.com/v1"
COGNEE_EMBEDDING_API_KEY="nvapi-..."
COGNEE_EMBEDDING_DIMENSIONS="4096"
```

The `hosted_vllm/` prefix on `COGNEE_LLM_MODEL` tells LiteLLM to use your endpoint. Commented blocks in `.env.example` show Ollama swap options.

---

## Project structure (this repo)

```
.
├── shellie/
│   ├── cli.py           # `shellie` entry point
│   ├── config.py        # Per-project .env loading
│   ├── paths.py         # Project root detection, .shellie/ paths
│   ├── agent.py         # LangChain agent + system prompt
│   ├── tools.py         # Shell, files, search, memory tools
│   ├── session_memory.py
│   ├── cognee_memory.py
│   ├── mcp/             # Optional MCP client + `shellie-mcp` CLI
│   ├── shell.py
│   └── ui.py
├── pyproject.toml
├── .env.example         # Template — copy to your project root
└── main.py              # Backward-compatible: python main.py
```

---

## Dependencies

LangChain, LangGraph (SQLite checkpointer), DuckDuckGo search, Wikipedia, python-dotenv, pydantic, httpx, beautifulsoup4, **ruff** (Python linting for `read_lint`). Optional: **Cognee** via `shellie[cognee]`; **MCP** via `shellie[mcp]` (`langchain-mcp-adapters` + `shellie-mcp`); **yamllint** via `shellie[lint]` or `pipx inject`. LLM backend is any supported provider configured in the **project's** `.env`.

---

## Uninstall

If you installed with pipx and want to remove Shellie:

```bash
pipx uninstall shellie
```

This removes the CLI and its pipx environment only. It does **not** delete project `.shellie/` folders or device memory under `~/.config/shellie` — remove those yourself if you want them gone.
