#!/usr/bin/env bash
# Reload the systemd user unit that owns 127.0.0.1:8743.
# After git pull / a new commit this is the update step — not kill+nohup.
#
# A Grok/Cursor session that was already connected still has the OLD tool
# list until that client restarts. Restart the unit here, then restart the
# agent session.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT="${MODEL_RADAR_UNIT:-model-radar.service}"
PORT="${MODEL_RADAR_PORT:-8743}"
TRIES="${MODEL_RADAR_WAIT_TRIES:-20}"
VENV_BIN="${MODEL_RADAR_VENV:-$ROOT/.venv/bin}"

old_pid="$(systemctl --user show -p MainPID --value "$UNIT" 2>/dev/null || echo 0)"
old_active="$(systemctl --user is-active "$UNIT" 2>/dev/null || echo unknown)"
pkg_ver="$("$VENV_BIN/python" -c "from model_radar import __version__; print(__version__)" 2>/dev/null || echo "?")"
git_head="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo "?")"
git_desc="$(git -C "$ROOT" log -1 --oneline 2>/dev/null || echo "")"

echo "before: unit=$UNIT active=$old_active pid=$old_pid"
echo "        package=$pkg_ver git=$git_head"
echo "        $git_desc"

# Stray copies (not the unit) steal the port. Do not touch the unit's MainPID.
strays="$(ps -eo pid=,args= | awk -v port="--port ${PORT}" -v keep="$old_pid" '
  $0 ~ /model-radar serve/ && $0 ~ port && $1 != keep { print $1 }
')"
if [ -n "$strays" ]; then
  echo "killing stray model-radar pids (not the unit): $strays"
  # shellcheck disable=SC2086
  kill $strays 2>/dev/null || true
  sleep 1
fi

systemctl --user restart "$UNIT"

for i in $(seq 1 "$TRIES"); do
  if timeout 1 bash -c "echo >/dev/tcp/127.0.0.1/${PORT}" 2>/dev/null; then
    new_pid="$(systemctl --user show -p MainPID --value "$UNIT")"
    echo "after:  pid=$new_pid (was $old_pid) listening 127.0.0.1:${PORT} (${i}s)"
    systemctl --user is-active "$UNIT"

    health=""
    for _ in $(seq 1 10); do
      if health="$("$VENV_BIN/python" - "$PORT" <<'PY'
import sys, urllib.request
port = sys.argv[1]
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=3) as r:
        print(r.read().decode())
except Exception as e:
    sys.exit(f"healthz failed: {e}")
PY
)"; then
        break
      fi
      health=""
      sleep 1
    done
    if [ -n "$health" ]; then
      echo "$health"
      echo "$health" | "$VENV_BIN/python" -c "
import json, sys
b = json.load(sys.stdin)
print('healthz version=', b.get('version'), 'still_free=', b.get('has_still_free'), 'tools=', len(b.get('tools') or []))
if not b.get('has_still_free'):
    sys.exit('still_free missing from live process — wrong build')
"
    else
      echo "warning: /healthz not up yet (old binary?). pid=$new_pid" >&2
    fi

    echo
    echo "Unit is new code. Restart the Grok/Cursor session so it re-lists tools."
    exit 0
  fi
  sleep 1
done

echo "timed out waiting for 127.0.0.1:${PORT}" >&2
systemctl --user --no-pager -l status "$UNIT" | tail -20 >&2
exit 1
