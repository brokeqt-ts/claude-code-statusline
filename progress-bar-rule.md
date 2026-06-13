# Progress-bar rule for CLAUDE.md

The status line can *render* a progress bar, but it never decides on its own that a
task is "long" and it does not compute progress — both are fed to it explicitly via
`task-bar.sh`. For the bar to appear automatically, the agent (Claude) must be told to
drive it. That instruction lives in your `CLAUDE.md`, not in `statusline.py`.

Copy the block below into `~/.claude/CLAUDE.md` (global, applies to every project) or
into a project's `CLAUDE.md` (applies to that project only).

---

```markdown
## Visual progress for long-running tasks — always

For ANY long-running task (a background process longer than ~30s: builds, deploys,
training, dataset builds, migrations, large batch edits, backtests) driving a live
progress bar is the DEFAULT, not an option:

1. **Status-line bar** via `bash ~/.claude/task-bar.sh` — start it when the process
   begins, update it per phase, clear it when done. Subcommands:
   - `task-bar.sh start <label> [phase]` — begin (captures start time for ETA)
   - `task-bar.sh set <phase> <current> <total>` — update phase + progress (bar, numbers, ETA)
   - `task-bar.sh pct <phase> <percent>` — update by percentage
   - `task-bar.sh phase <phase>` — change phase label (spinner, no numbers)
   - `task-bar.sh warn|error <msg>` — mark warning/error state
   - `task-bar.sh done` — clear the marker (task finished)
2. **Feed real progress.** The bar shows nothing useful unless someone feeds it numbers.
   Either the task calls the helper itself, or — for a process whose progress lives in a
   log — parse the log periodically and call `task-bar.sh set <phase> N M` so the bar
   stays live across every phase. On finish or failure, call `task-bar.sh done` (or `error`).

Do not settle for just printing a path to a log file — show the bar.
```

---

## Notes

- The helper reads `$CLAUDE_CODE_SESSION_ID` so the bar shows only in the session that
  started it. Nothing extra to configure — Claude Code sets that variable.
- A stale marker (older than 15 min) is ignored by `statusline.py`, so a crashed process
  won't leave a frozen bar — but you should still call `done`/`error` explicitly.
- This rule is plain guidance for the agent. It changes the agent's *behaviour*; it has
  no effect on the `statusline.py` renderer, which works the same with or without it.
