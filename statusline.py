"""Claude Code status line: ASCII context bar with color.

Reads session JSON from stdin, parses transcript_path JSONL for the last
assistant usage, computes context % vs model limit, prints a coloured bar.

Output format:  ctx ████████░░ 78% (156k/200k)
Color: green <50%, yellow 50-75%, red >=75%.

Tested on Windows PowerShell + Windows Terminal (ANSI supported since 1903).
Cross-platform RAM: Windows (ctypes), Linux (/proc/meminfo), macOS (sysctl+vm_stat).

Env overrides:
  CLAUDE_STATUSLINE_OPUS_LIMIT    — context limit for opus models (default 200000)
  CLAUDE_STATUSLINE_CONTEXT_LIMIT — context limit override for any model
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Model context window limits (input + cache_creation + cache_read).
LIMITS: dict[str, int] = {
    "claude-opus-4-8[1m]": 1_000_000,
    "claude-opus-4-8": 200_000,
    "claude-opus-4-7[1m]": 1_000_000,
    "claude-opus-4-7": 200_000,
    "claude-opus-4-6": 200_000,
    "claude-opus-4-5": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-sonnet-4-5": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "claude-haiku-4-5": 200_000,
}
DEFAULT_LIMIT = 200_000

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
GREY = "\033[90m"
CYAN = "\033[36m"
RESET = "\033[0m"
BOLD = "\033[1m"
# Яркие (bright) варианты — для контекстных цифр, чтобы выделялись.
BGREEN = "\033[92m"
BYELLOW = "\033[93m"
BRED = "\033[91m"
BWHITE = "\033[97m"
BMAGENTA = "\033[95m"

# Claude Pro/Max rolling usage window. Real reset is more complex
# (per-message rolling), but elapsed-since-first-message is a reasonable
# user-facing approximation: when it hits 0, the window has rolled.
SESSION_WINDOW_SEC = 5 * 3600

# Размер хвостового блока для last_usage(): читаем последние ~1МБ файла.
_TAIL_BYTES = 1_048_576


def fmt_k(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n // 1000}k"
    return str(n)


def session_start(transcript_path: str) -> datetime | None:
    """Return the earliest timestamp in the transcript JSONL, or None.

    Records are appended chronologically, so the first record with a
    `timestamp` field is the session start. Returns timezone-aware datetime.
    """
    if not transcript_path:
        return None
    p = Path(transcript_path)
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                ts = obj.get("timestamp")
                if isinstance(ts, str):
                    try:
                        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except ValueError:
                        continue
    except OSError:
        return None
    return None


def fmt_duration(seconds: int) -> str:
    if seconds <= 0:
        return "0m"
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h > 0:
        return f"{h}h{m:02d}m"
    return f"{m}m"


def shorten_model(model_id: str, display_name: str = "") -> str:
    """Turn 'claude-opus-4-7[1m]' into 'opus-4.7 [1m]'."""
    if display_name:
        return display_name
    if not model_id:
        return "?"
    s = model_id
    if s.startswith("claude-"):
        s = s[len("claude-"):]
    # Split off bracket suffix like '[1m]'
    head, sep, tail = s.partition("[")
    parts = head.split("-")
    # Recognise '<family>-<major>-<minor>' and turn into '<family>-<major>.<minor>'.
    if (len(parts) >= 3
            and parts[0] in ("opus", "sonnet", "haiku")
            and parts[1].isdigit()
            and parts[2].isdigit()):
        head = f"{parts[0]}-{parts[1]}.{parts[2]}"
    if sep:
        return f"{head} [{tail}"
    return head


def last_usage(transcript_path: str) -> dict | None:
    """Walk the JSONL transcript tail, return the most recent assistant usage dict.

    Читает только последние ~1МБ файла (seek с конца), чтобы не парсить сотни МБ
    при каждом обновлении статуслайна (вызов каждые 5с).
    """
    if not transcript_path:
        return None
    p = Path(transcript_path)
    if not p.exists():
        return None
    try:
        with p.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            offset = max(0, size - _TAIL_BYTES)
            f.seek(offset)
            raw = f.read()
        # Декодируем, отбрасывая неполную первую строку (если offset > 0).
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if offset > 0 and lines:
            lines = lines[1:]  # первая строка может быть обрезана
    except OSError:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("type") != "assistant":
            continue
        msg = obj.get("message")
        if not isinstance(msg, dict):
            continue
        u = msg.get("usage")
        if isinstance(u, dict):
            return u
    return None


def ram_segment() -> str:
    """Сегмент свободной RAM: free/total G, цвет по запасу, предупреждение если <4 ГБ.

    Windows — ctypes GlobalMemoryStatusEx; Linux — /proc/meminfo;
    macOS — sysctl + vm_stat. Без внешних зависимостей. При любой ошибке — пустая строка.
    """
    import platform
    system = platform.system()
    try:
        if system == "Windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            m = MEMORYSTATUSEX()
            m.dwLength = ctypes.sizeof(m)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return ""
            free = m.ullAvailPhys / 1073741824.0
            tot = m.ullTotalPhys / 1073741824.0

        elif system == "Linux":
            info: dict[str, int] = {}
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                for ln in fh:
                    k, _, v = ln.partition(":")
                    v = v.strip().split()[0]
                    info[k.strip()] = int(v)
            # MemAvailable — более точная оценка, чем MemFree+Buffers+Cached.
            avail = info.get("MemAvailable", info.get("MemFree", 0))
            total = info.get("MemTotal", 0)
            if total == 0:
                return ""
            free = avail / 1048576.0  # кБ → ГБ
            tot = total / 1048576.0

        elif system == "Darwin":
            import subprocess
            hw = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
            tot = int(hw) / 1073741824.0
            vm = subprocess.check_output(["vm_stat"], text=True)
            page_size = 4096
            free_pages = inactive_pages = 0
            for ln in vm.splitlines():
                if ln.startswith("Mach Virtual Memory Statistics"):
                    # Строка вида "page size of 16384 bytes"
                    import re
                    m = re.search(r"page size of (\d+) bytes", ln)
                    if m:
                        page_size = int(m.group(1))
                elif "Pages free:" in ln:
                    free_pages = int(ln.split(":")[1].strip().rstrip("."))
                elif "Pages inactive:" in ln:
                    inactive_pages = int(ln.split(":")[1].strip().rstrip("."))
            free = (free_pages + inactive_pages) * page_size / 1073741824.0

        else:
            return ""

        col = RED if free < 4 else (YELLOW if free < 8 else GREEN)
        warn = " !" if free < 4 else ""
        return f" {GREY}·{RESET} {col}\U0001f9e0 {free:.1f}/{tot:.0f}G{warn}{RESET}"
    except Exception:
        return ""


def _fmt_eta(sec: float) -> str:
    sec = int(max(0, sec))
    if sec < 60:
        return f"{sec}s"
    m = sec // 60
    if m < 60:
        return f"{m}m"
    return f"{m // 60}h{m % 60:02d}m"


_STATUS_COLOR = {"running": BMAGENTA, "warn": BYELLOW, "error": BRED, "done": BGREEN}
_STATUS_ICON = {"running": "⏳", "warn": "⚠", "error": "✗", "done": "✓"}
_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def task_segment(session_id: str) -> str:
    """Прогресс-бар активной долгой задачи из ~/.claude/.statusline_task.

    Формат — JSON (предпочтительно) ИЛИ legacy-TSV (одна строка).
    JSON-поля: label, phase, current, total, percent, start_ts (epoch-сек для ETA),
    status (running|warn|error|done), session_id (бар виден ТОЛЬКО в этой сессии).
    TSV: "label\\tcurrent\\ttotal" | "label\\tpercent" | "label" (без session-привязки).

    Возможности: ETA (из start_ts+%), current/total, статус-цвет/иконка, спиннер для
    неопределённого прогресса (нет total/percent). Маркер старше 15 мин игнорируется
    (мёртвый процесс не висит). Бар с чужим session_id не показывается.
    """
    try:
        import time, json as _json
        p = Path.home() / ".claude" / ".statusline_task"
        if not p.exists() or time.time() - p.stat().st_mtime > 900:
            return ""
        raw = p.read_text(encoding="utf-8").strip()
        if not raw:
            return ""

        label, phase, status = "task", "", "running"
        cur = tot = pct = start_ts = None
        owner = None
        if raw.startswith("{"):
            d = _json.loads(raw)
            owner = d.get("session_id")
            label = str(d.get("label") or "task")
            phase = str(d.get("phase") or "")
            cur, tot = d.get("current"), d.get("total")
            pct = d.get("percent")
            start_ts = d.get("start_ts")
            status = str(d.get("status") or "running")
        else:
            parts = raw.split("\t")
            label = parts[0].strip() or "task"
            try:
                if len(parts) >= 3:
                    cur, tot = float(parts[1]), float(parts[2])
                elif len(parts) == 2:
                    pct = float(parts[1])
            except ValueError:
                pass

        # session-привязка: маркер с чужим session_id не показываем в этой сессии
        if owner and session_id and str(owner) != str(session_id):
            return ""

        if pct is None and cur is not None and tot:
            try:
                pct = float(cur) / float(tot) * 100.0
            except (ValueError, ZeroDivisionError):
                pct = None

        scol = _STATUS_COLOR.get(status, BMAGENTA)
        sicon = _STATUS_ICON.get(status, "⏳")
        head = label + (f" › {phase}" if phase else "")

        # неопределённый прогресс → спиннер (по времени; running) либо статус-иконка
        if pct is None:
            ch = _SPINNER[int(time.time() * 1.25) % len(_SPINNER)] if status == "running" else sicon
            return f" {GREY}·{RESET} {scol}{ch} {head}{RESET}"

        pct = max(0.0, min(100.0, pct))
        w = 12
        fill = int(pct / (100.0 / w))
        bar = "█" * fill + "░" * (w - fill)
        ct = f" {int(cur)}/{int(tot)}" if (cur is not None and tot) else ""
        eta = ""
        if start_ts and pct > 0:
            try:
                rem = (time.time() - float(start_ts)) * (100.0 - pct) / pct
                eta = f" ~{_fmt_eta(rem)}"
            except (ValueError, ZeroDivisionError):
                pass
        return (
            f" {GREY}·{RESET} {scol}{sicon} {head}{RESET} {scol}{bar}{RESET} "
            f"{BOLD}{scol}{pct:.0f}%{RESET}{GREY}{ct}{eta}{RESET}"
        )
    except Exception:
        return ""


def _resolve_limit(model_id: str, model_display_raw: str) -> int:
    """Определить лимит контекста с учётом env-оверрайдов.

    Приоритет: CLAUDE_STATUSLINE_CONTEXT_LIMIT > CLAUDE_STATUSLINE_OPUS_LIMIT (для opus)
    > LIMITS-таблица > DEFAULT_LIMIT.
    """
    # Общий оверрайд для любой модели.
    global_override = os.environ.get("CLAUDE_STATUSLINE_CONTEXT_LIMIT", "").strip()
    if global_override:
        try:
            return int(global_override)
        except ValueError:
            pass

    is_opus = "opus" in (model_id or "").lower() or "opus" in (model_display_raw or "").lower()
    if is_opus:
        opus_env = os.environ.get("CLAUDE_STATUSLINE_OPUS_LIMIT", "").strip()
        if opus_env:
            try:
                return int(opus_env)
            except ValueError:
                pass
        # Публичный дефолт для opus — 200k (как и у остальных моделей).
        return LIMITS.get(model_id, DEFAULT_LIMIT)

    return LIMITS.get(model_id, DEFAULT_LIMIT)


def main() -> None:
    # Reconfigure stdout for UTF-8 (bar chars + colour codes).
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    try:
        raw = sys.stdin.read().lstrip("﻿")
        data = json.loads(raw) if raw.strip() else {}
    except (ValueError, OSError):
        data = {}

    model = data.get("model") or {}
    model_id = model.get("id", "") if isinstance(model, dict) else ""
    model_display_raw = model.get("display_name", "") if isinstance(model, dict) else ""
    model_label = shorten_model(model_id, model_display_raw)
    transcript = data.get("transcript_path", "")

    start = session_start(transcript)
    if start is not None:
        age_sec = (datetime.now(timezone.utc) - start).total_seconds()
        remaining = max(0, SESSION_WINDOW_SEC - int(age_sec))
        reset_str = "OK" if remaining == 0 else fmt_duration(remaining)
    else:
        reset_str = "?"

    limit = _resolve_limit(model_id, model_display_raw)

    used = 0
    u = last_usage(transcript)
    if u is not None:
        used = (
            int(u.get("input_tokens", 0) or 0)
            + int(u.get("cache_creation_input_tokens", 0) or 0)
            + int(u.get("cache_read_input_tokens", 0) or 0)
        )

    pct = (used / limit * 100.0) if limit > 0 else 0.0
    pct_clamped = min(pct, 999.0)
    pct_int = int(round(pct_clamped))

    # Контекст — яркими жирными цифрами (без бара): бар отдан под прогресс задачи.
    if pct < 50:
        cctx = BGREEN
    elif pct < 75:
        cctx = BYELLOW
    else:
        cctx = BRED

    out = (
        f"{GREY}ctx{RESET} {BOLD}{cctx}{pct_int}%{RESET} "
        f"{BOLD}{BWHITE}{fmt_k(used)}/{fmt_k(limit)}{RESET} "
        f"{GREY}·{RESET} {CYAN}{model_label}{RESET} "
        f"{GREY}· reset {reset_str}{RESET}"
        f"{ram_segment()}{task_segment(data.get('session_id', ''))}"
    )
    print(out, end="")


if __name__ == "__main__":
    main()
