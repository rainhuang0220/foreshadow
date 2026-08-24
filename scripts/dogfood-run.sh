#!/usr/bin/env bash
# One P0 dogfood day. Never edits scoring config. Empty Top 5 is success.
set -uo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOCAL="$ROOT/dogfood/local"
mkdir -p "$LOCAL"

UTC_DATE="$(date -u +%Y-%m-%d)"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
JOURNAL="$LOCAL/JOURNAL.md"
META="$LOCAL/${UTC_DATE}.meta.json"
LOG="$LOCAL/${UTC_DATE}.run.log"

# Refuse to touch scoring knobs.
if git diff --quiet -- examples/config.toml src/foreshadow/config.py 2>/dev/null; then
  :
fi

{
  echo
  echo "## ${STAMP}"
  echo
  echo "- cwd: \`${ROOT}\`"
  echo "- utc_date: \`${UTC_DATE}\`"
} >>"$JOURNAL"

export FORESHADOW_HOME="${FORESHADOW_HOME:-$LOCAL/home}"
mkdir -p "$FORESHADOW_HOME"

# Token: env, else gh. Do not print it.
if [ -z "${GITHUB_TOKEN:-}" ] && [ -z "${GH_TOKEN:-}" ]; then
  if command -v gh >/dev/null 2>&1; then
    if ! gh auth token >/dev/null 2>&1; then
      echo "- anomaly: missing GitHub token (gh auth token failed)" >>"$JOURNAL"
      echo "{\"utc_date\":\"$UTC_DATE\",\"ok\":false,\"anomaly\":\"missing_token\"}" >"$META"
      echo "missing GitHub token" >&2
      exit 2
    fi
  fi
fi

set +e
uv run foreshadow run >"$LOG" 2>&1
RC=$?
set -e

echo "- exit: \`${RC}\`" >>"$JOURNAL"

REPORT_DIR="$FORESHADOW_HOME/reports"
MD="$REPORT_DIR/${UTC_DATE}.md"
JSON="$REPORT_DIR/${UTC_DATE}.json"

if [ -f "$MD" ]; then
  cp "$MD" "$LOCAL/${UTC_DATE}.md"
  echo "- report_md: \`dogfood/local/${UTC_DATE}.md\`" >>"$JOURNAL"
fi
if [ -f "$JSON" ]; then
  cp "$JSON" "$LOCAL/${UTC_DATE}.json"
  echo "- report_json: \`dogfood/local/${UTC_DATE}.json\`" >>"$JOURNAL"
fi

python3 - "$RC" "$UTC_DATE" "$JSON" "$META" "$JOURNAL" "$LOG" <<'PY'
import json, sys, pathlib
rc = int(sys.argv[1])
utc_date = sys.argv[2]
json_path = pathlib.Path(sys.argv[3])
meta_path = pathlib.Path(sys.argv[4])
journal = pathlib.Path(sys.argv[5])
log_path = pathlib.Path(sys.argv[6])

payload = {}
if json_path.exists():
    try:
        payload = json.loads(json_path.read_text())
    except Exception as e:
        payload = {"_parse_error": str(e)}

status = payload.get("status")
top5 = payload.get("top5_count")
reason = payload.get("reason")
health = payload.get("source_health") or {}
anomalies = []
if rc != 0:
    anomalies.append(f"exit_{rc}")
if payload.get("_parse_error"):
    anomalies.append("json_parse")
if status == "degraded":
    anomalies.append("degraded")
if health.get("budget_abort"):
    anomalies.append("budget_abort")
if health.get("search_truncated"):
    anomalies.append("search_truncated")
if health.get("hydrate_failed"):
    anomalies.append("hydrate_failed")
if health.get("watchlist_truncated"):
    anomalies.append("watchlist_truncated")
# Empty Top 5 is NOT an anomaly.
notes = []
if top5 == 0:
    notes.append("empty_top5_success")

meta = {
    "utc_date": utc_date,
    "ok": rc == 0,
    "exit": rc,
    "status": status,
    "top5_count": top5,
    "reason": reason,
    "source_health": health,
    "anomalies": anomalies,
    "notes": notes,
}
meta_path.write_text(json.dumps(meta, indent=2) + "\n")

lines = [
    f"- status: `{status}`",
    f"- top5_count: `{top5}`",
]
if reason:
    lines.append(f"- reason: `{reason}`")
if notes:
    lines.append(f"- notes: {', '.join(notes)}")
if anomalies:
    lines.append(f"- **anomalies:** {', '.join(anomalies)}")
else:
    lines.append("- anomalies: none")
tail = log_path.read_text(errors="replace").strip().splitlines()[-12:]
if tail:
    lines.append("- log tail:")
    lines.append("")
    lines.append("```")
    lines.extend(tail)
    lines.append("```")
journal.write_text(journal.read_text() + "\n".join(lines) + "\n")
PY

exit "$RC"
