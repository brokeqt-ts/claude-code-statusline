#!/usr/bin/env bash
# Хелпер прогресс-бара статуслайна для долгих задач.
# Пишет ~/.claude/.statusline_task (JSON, привязан к $CLAUDE_CODE_SESSION_ID),
# который рисует statusline.py как ⏳-бар. Сохраняет start_ts между обновлениями
# (для ETA). Использование:
#   task-bar.sh start <label> [phase]            — начать (спиннер), зафиксировать start_ts
#   task-bar.sh set   <phase> <current> <total>  — обновить фазу+прогресс (бар, ETA)
#   task-bar.sh pct   <phase> <percent>          — обновить по проценту
#   task-bar.sh phase <phase>                    — сменить фазу без чисел (спиннер)
#   task-bar.sh warn|error <msg>                 — статус warn/error
#   task-bar.sh done                             — стереть маркер (задача завершена)
#
# session_id: если CLAUDE_CODE_SESSION_ID пуст — поле session_id НЕ пишется в JSON,
# и бар виден во всех сессиях. Если задан — пишется, и бар показывается только в ней.
set -u
# UTF-8 для argv/вывода python: на Windows argv иначе декодируется как cp1251 (mbcs)
# и юникод в label/phase (кириллица и пр.) превращается в mojibake/U+FFFD.
export PYTHONUTF8=1
F="$HOME/.claude/.statusline_task"
SID="${CLAUDE_CODE_SESSION_ID:-}"
cmd="${1:-}"; shift || true

# Выбрать интерпретатор python: предпочитаем python3 (Linux/macOS), fallback python (Windows git-bash).
_py(){ command -v python3 >/dev/null 2>&1 && echo python3 || echo python; }

# Прочитать поле из текущего маркера (для сохранения label/start_ts между вызовами).
# Используем python json.load — безопасно для экранированных значений.
_get(){
  [ -f "$F" ] || return 0
  $(_py) - "$1" "$F" <<'PYEOF'
import sys, json
key, path = sys.argv[1], sys.argv[2]
try:
    with open(path, encoding='utf-8') as fh:
        d = json.load(fh)
    v = d.get(key)
    if v is not None:
        print(v, end='')
except Exception:
    pass
PYEOF
}

_now(){ date +%s; }

# Записать JSON-маркер через python json.dumps: все значения передаются как аргументы,
# строковая интерполяция в JSON-тело не используется — кавычки/бэкслеши/$ безопасны.
# Аргументы: session_id label phase current total percent start_ts status pid
# Пустая строка "" для числовых полей (current/total/percent/start_ts/pid) = поле не включается.
# pid (из $TASKBAR_PID): PID долгоживущего писателя; statusline скрывает бар, если он мёртв
# (orphan/краш без `done`) — сразу, не ждать 15 мин. Пусто → старое поведение по давности.
_write_marker(){
  $(_py) - "$@" <<'PYEOF'
import sys, json
# argv: sid label phase current total percent start_ts status pid
sid, label, phase, current, total, percent, start_ts, status, pid = sys.argv[1:10]
d = {"label": label, "phase": phase, "status": status}
if sid:
    d["session_id"] = sid
if current != "":
    d["current"] = float(current)
if total != "":
    d["total"] = float(total)
if percent != "":
    d["percent"] = float(percent)
if start_ts != "":
    d["start_ts"] = int(start_ts)
if pid != "":
    d["pid"] = int(pid)
print(json.dumps(d, ensure_ascii=False), end='')
PYEOF
}
TBPID="${TASKBAR_PID:-}"

label="$(_get label)"; start="$(_get start_ts)"
[ -z "${start:-}" ] && start="$(_now)"

case "$cmd" in
  start)
    label="${1:-task}"; phase="${2:-}"
    _write_marker "$SID" "$label" "$phase" "" "" "" "$(_now)" "running" "$TBPID" > "$F" ;;
  set)
    phase="${1:-}"; cur="${2:-0}"; tot="${3:-0}"
    _write_marker "$SID" "${label:-task}" "$phase" "$cur" "$tot" "" "$start" "running" "$TBPID" > "$F" ;;
  pct)
    phase="${1:-}"; p="${2:-0}"
    _write_marker "$SID" "${label:-task}" "$phase" "" "" "$p" "$start" "running" "$TBPID" > "$F" ;;
  phase)
    phase="${1:-}"
    _write_marker "$SID" "${label:-task}" "$phase" "" "" "" "$start" "running" "$TBPID" > "$F" ;;
  warn|error)
    _write_marker "$SID" "${label:-task} ${1:-}" "" "" "" "" "" "$cmd" "$TBPID" > "$F" ;;
  done)
    rm -f "$F" ;;
  *)
    echo "usage: task-bar.sh start|set|pct|phase|warn|error|done ..." >&2; exit 2 ;;
esac
