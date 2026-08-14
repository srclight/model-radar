#!/usr/bin/env bash
# Restart the systemd user unit that owns 127.0.0.1:8743.
# Do not kill + nohup a second copy — the unit will fight you for the port.
set -euo pipefail

UNIT="${MODEL_RADAR_UNIT:-model-radar.service}"
PORT="${MODEL_RADAR_PORT:-8743}"
TRIES="${MODEL_RADAR_WAIT_TRIES:-20}"

systemctl --user restart "$UNIT"

for i in $(seq 1 "$TRIES"); do
  # /sse streams forever — only check that the port accepts a TCP connect.
  if timeout 1 bash -c "echo >/dev/tcp/127.0.0.1/${PORT}" 2>/dev/null; then
    echo "$UNIT is listening on 127.0.0.1:${PORT} (${i}s)"
    systemctl --user is-active "$UNIT"
    exit 0
  fi
  sleep 1
done

echo "timed out waiting for 127.0.0.1:${PORT}" >&2
systemctl --user --no-pager -l status "$UNIT" | tail -20 >&2
exit 1
