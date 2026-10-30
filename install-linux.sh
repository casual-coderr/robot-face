#!/usr/bin/env bash
# Installs the robot face server as a systemd service: starts at boot, restarts if it crashes.
# Run it once on the Linux PC, from inside the copied robot-face folder:
#
#   bash install-linux.sh
#
# Undo with:  sudo systemctl disable --now robotface && sudo rm /etc/systemd/system/robotface.service

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="${SUDO_USER:-$(id -un)}"
PORT=8765
SERVICE=/etc/systemd/system/robotface.service

PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "python3 not found. Install it first (e.g. sudo apt install python3)." >&2
  exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)'; then
  echo "Python 3.7 or newer is needed (found: $("$PY" --version))." >&2
  exit 1
fi
if [ ! -f "$DIR/server.py" ]; then
  echo "server.py not found in $DIR - run this from the robot-face folder." >&2
  exit 1
fi

echo "Installing service for user '$RUN_USER' in $DIR using $PY"

sudo tee "$SERVICE" >/dev/null <<EOF
[Unit]
Description=Robot face server
After=network-online.target
Wants=network-online.target

[Service]
User=$RUN_USER
WorkingDirectory=$DIR
ExecStart=$PY $DIR/server.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now robotface

# open the port if a firewall that we know about is active
if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow "$PORT"/tcp
fi

sleep 2
if systemctl is-active --quiet robotface; then
  IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  echo
  echo "Running. Open  http://${IP:-this-pc}:$PORT/  from the panel."
  echo "Logs:    journalctl -u robotface -f"
  echo "Restart: sudo systemctl restart robotface"
else
  echo "The service did not start. Check:  journalctl -u robotface -n 50" >&2
  exit 1
fi
