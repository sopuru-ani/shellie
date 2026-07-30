---
name: research-build
description: >-
  Research a topic then produce a deliverable from saved notes (site, doc,
  code, report, or other). Use when the user asks to research and
  build/write/implement, or when work must be grounded in sources rather than
  memory. Not limited to webapps.
---

# Research → build

Research lives on disk. The chat is the control plane — do not keep full article
bodies only in conversation.

## When this skill applies

- “Research X and build/write/implement Y”
- Deliverables that need current or cited facts (sites, guides, scripts, reports)
- Any domain: web or non-web

If a stack/design skill also matches the deliverable (e.g. `webapp`,
`frontend-design`), activate those **after** research notes exist, then build.

## Where to store notes

Project-local (not the Shellie install dir):

```text
.shellie/research/<slug>/
  QUESTIONS.md    # what we need to answer
  SOURCES.md      # url + one-line why it matters
  NOTES.md        # facts, quotes, stats (with source refs)
  OUTLINE.md      # structure of the deliverable
  DECISIONS.md    # optional: choices distilled from research
```

`<slug>` = short topic name from the brief (e.g. `obsidian-coffee`, `fed-dnf`).

Prefer `.shellie/research/` so notes stay with session/Cognee data. Remind the
user once that `.shellie/` should be in `.gitignore` so research does not slip
into git — do not force a commit of that change unless they ask.

## Procedure

### 1. Scope

Clarify the deliverable and 3–8 research questions. Write them to `QUESTIONS.md`.
Keep this short — do not interview forever.

### 2. Research → files

- Use `search` / `wikipedia` / `web_fetch` as needed.
- Prefer search → pick useful URLs → `web_fetch` (use `start=` to continue long pages).
- After each useful batch, **update** `SOURCES.md` and `NOTES.md` with
  `file_write` / `file_edit`. Summarize; do not dump raw pages into chat.
- Source count is **flexible**: gather enough to ground the deliverable. Thin
  topics may need few sources; broad ones need more. Do not pad with junk URLs.
- Do not re-fetch the same URL in a loop — read your notes instead.

### 3. Synthesize

From `NOTES.md`, write `OUTLINE.md` (and `DECISIONS.md` if choices matter).
Checkpoint here if the turn is long: tell the user notes are ready and continue
building next message if needed. Prefer disk checkpoints over shipping a thin
product because of step limits.

### 4. Build from notes

Implement the deliverable **from** `.shellie/research/<slug>/` files:

- Web → activate `webapp` / `frontend-design` if available; pull copy and facts
  from notes into pages.
- Doc/report → write the document from `OUTLINE.md` + `NOTES.md`.
- Code/tooling → implement from requirements in `DECISIONS.md` / outline.

Important claims in the deliverable should map to `NOTES.md` / `SOURCES.md`,
or be clearly labeled as assumption / unknown.

### 5. Verify

- Research files exist and are non-empty before calling the work done.
- Spot-check a few deliverable claims against `NOTES.md`.
- Lint / build as appropriate (`read_lint`, `npm run build`, etc.).

## Must not

- Research in chat only, then invent a short deliverable from memory.
- Skip writing notes because “context still fits.”
- Treat a step-limit as permission to ship an empty/thin result — write what you
  have to disk and continue.

## Anti-patterns

- Pasting entire `web_fetch` bodies into the user reply
- One mega turn that never creates `.shellie/research/`
- Ignoring notes while building
- Hard-requiring an arbitrary number of sources when fewer suffice
