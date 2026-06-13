# claude-code-statusline

A lightweight status line for [Claude Code](https://claude.ai/code) that shows:

- **Context usage** — percentage and token counts vs the real context-window limit (auto-detected, colour-coded)
- **Active model** — short human-readable name
- **RAM** — free / total (Windows, Linux, macOS; no extra dependencies)
- **Task progress bar** — for long-running operations via `task-bar.sh`

Example output (rendered in terminal with ANSI colour):

```
ctx 23% 46k/200k · sonnet-4.6 · 🧠 14.2/32G · ⏳ Build › compile ████████░░░░ 67% 2/3 ~45s
```

> **Installing via Claude Code?** Point Claude at this README and ask it to set up the
> status line, then follow the numbered steps **in order**. **Step 3 is what makes the
> progress bar actually appear** — the status line only *renders* a bar; it never decides
> a task is "long" or computes progress on its own. Without the rule from Step 3 the agent
> won't drive the bar and you'll only ever see the context / model / RAM segments.

---

## Requirements

- **Python 3** (`python3` or `python` on PATH)
- **Bash** — for `task-bar.sh` only (git-bash on Windows, or any POSIX shell)
- No third-party packages required

---

## Installation

### 1. Copy the files

Place `statusline.py` and (optionally) `task-bar.sh` anywhere accessible. A common location is `~/.claude/`.

### 2. Configure Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "command": "python3 /home/you/.claude/statusline.py",
    "refreshInterval": 5
  }
}
```

On Windows with git-bash `python` (no `python3`):

```json
{
  "statusLine": {
    "command": "python C:/Users/you/.claude/statusline.py",
    "refreshInterval": 5
  }
}
```

Claude Code feeds session JSON to the command via **stdin** and displays whatever is printed to **stdout**.

### 3. Enable automatic progress bars (recommended)

This step is what makes the progress bar appear during long tasks. The status line is a
passive renderer — it draws a bar only when something feeds it progress via `task-bar.sh`,
and nothing feeds it unless the agent is told to. That instruction is a short rule for
Claude, kept in your `CLAUDE.md`.

Append the contents of [`progress-bar-rule.md`](progress-bar-rule.md) (the fenced block
inside it) to one of:

- `~/.claude/CLAUDE.md` — applies to every project, or
- a project's `CLAUDE.md` — applies to that project only.

**Doing this install through Claude Code?** Ask it to *"also add the progress-bar rule from
`progress-bar-rule.md` to my `~/.claude/CLAUDE.md`"* — it will append the rule block for you.
Skip this step if you'd rather drive `task-bar.sh` manually from your own scripts.

---

## task-bar.sh — progress bar for long tasks

`task-bar.sh` writes `~/.claude/.statusline_task` (a JSON marker), which `statusline.py` picks up and renders as a progress bar.

### Subcommands

| Command | Description |
|---|---|
| `task-bar.sh start <label> [phase]` | Begin a task (spinner). Captures start time for ETA. |
| `task-bar.sh set <phase> <current> <total>` | Update phase + numeric progress (shows bar + ETA). |
| `task-bar.sh pct <phase> <percent>` | Update by percentage. |
| `task-bar.sh phase <phase>` | Change phase label (spinner, no numbers). |
| `task-bar.sh warn <msg>` | Mark task as warning state. |
| `task-bar.sh error <msg>` | Mark task as error state. |
| `task-bar.sh done` | Remove marker (task finished). |

### Usage example

```bash
source task-bar.sh  # or call directly

task-bar.sh start "Deploy" "build"
cargo build --release
task-bar.sh set "upload" 1 3
rsync ...
task-bar.sh set "restart" 2 3
ssh prod pm2 restart app
task-bar.sh done
```

### Session binding

If `CLAUDE_CODE_SESSION_ID` is set in the environment, the marker is bound to that session — the bar appears only in the Claude Code session that wrote it. If the variable is empty, the bar is visible in all sessions.

### Making Claude call it automatically

Calling `task-bar.sh` by hand is fine, but the usual goal is for Claude to drive the bar
on its own whenever it starts a long task. That is a behavioural rule, not code — add it to
your `CLAUDE.md` as described in [Installation Step 3](#3-enable-automatic-progress-bars-recommended).
The ready-to-paste rule lives in [`progress-bar-rule.md`](progress-bar-rule.md).

---

## Context limit — auto-detected

The real context-window size and usage are read **directly from the JSON Claude Code feeds on stdin** (`context_window.context_window_size`, `total_input_tokens`, `used_percentage`). No configuration needed — a 1M-context plan shows `/1.0M`, a standard plan `/200k`, automatically.

### Environment overrides (optional — legacy/fallback)

Only needed on **older Claude Code versions** that don't send `context_window` on stdin (the script then falls back to a model→limit table + transcript parsing).

| Variable | Description |
|---|---|
| `CLAUDE_STATUSLINE_OPUS_LIMIT` | Fallback context limit for opus models (default 200000). |
| `CLAUDE_STATUSLINE_CONTEXT_LIMIT` | Fallback override for **any** model. |

---

## Cross-platform support

| Platform | Context bar | RAM segment |
|---|---|---|
| Windows | Yes | `ctypes` GlobalMemoryStatusEx |
| Linux | Yes | `/proc/meminfo` |
| macOS | Yes | `sysctl hw.memsize` + `vm_stat` |

The RAM segment is silently omitted on any unsupported OS or if the system call fails.

---

## How context % is computed

Primary path: read straight from the `context_window` object Claude Code sends on stdin (`used_percentage`, `total_input_tokens`, `context_window_size`) — exact and zero-cost.

Fallback (older Claude Code without `context_window`): read the last `assistant` message in the transcript JSONL and sum `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`, against the model→limit table. Only the tail (~1 MB) of the transcript is read — safe for long sessions.

---

## License

MIT — see [LICENSE](LICENSE).
