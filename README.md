# claude-code-statusline

A lightweight status line for [Claude Code](https://claude.ai/code) that shows:

- **Context usage** — percentage and token counts vs model limit (colour-coded)
- **Active model** — short human-readable name
- **Reset window** — time remaining in the 5-hour rolling usage window
- **RAM** — free / total (Windows, Linux, macOS; no extra dependencies)
- **Task progress bar** — for long-running operations via `task-bar.sh`

Example output (rendered in terminal with ANSI colour):

```
ctx 23% 46k/200k · sonnet-4.6 · reset 3h12m · 🧠 14.2/32G · ⏳ Build › compile ████████░░░░ 67% 2/3 ~45s
```

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

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `CLAUDE_STATUSLINE_OPUS_LIMIT` | `200000` | Context limit for opus models. Set to `1000000` if you have a 1M-context plan. |
| `CLAUDE_STATUSLINE_CONTEXT_LIMIT` | — | Override context limit for **any** model. Takes priority over everything. |

Example — set a 1M opus limit in your shell profile:

```bash
export CLAUDE_STATUSLINE_OPUS_LIMIT=1000000
```

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

The script reads the last `assistant` message in the session transcript JSONL and sums:

```
input_tokens + cache_creation_input_tokens + cache_read_input_tokens
```

Only the tail (~1 MB) of the transcript is read on each refresh — safe for long sessions with large files.

---

## License

MIT — see [LICENSE](LICENSE).
