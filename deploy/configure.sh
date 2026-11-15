#!/usr/bin/env bash
# Run as root after code, both frontend builds and hello-agents are installed.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
    echo 'Run with sudo.' >&2
    exit 1
fi
roco_root=/opt/roco/app
test -x /opt/roco/conda/envs/hello-agents/bin/python
test -f "$roco_root/web/dist/index.html"
test -f /opt/roco/public/index.html
getent passwd roco >/dev/null || useradd --system --home /opt/roco --shell /usr/sbin/nologin roco
mkdir -p "$roco_root/logs" /etc/roco
chown -R roco:roco "$roco_root/data" "$roco_root/logs"
install -m 644 "$roco_root/deploy/roco.service" /etc/systemd/system/roco.service
install -m 644 "$roco_root/deploy/nginx.conf" /etc/nginx/sites-available/roco
ln -sfn /etc/nginx/sites-available/roco /etc/nginx/sites-enabled/roco
if [ -L /etc/nginx/sites-enabled/default ]; then
    unlink /etc/nginx/sites-enabled/default
fi
nginx -t
systemctl daemon-reload
systemctl enable --now roco nginx
systemctl restart roco
for attempt in $(seq 1 20); do
    if curl -fsS http://127.0.0.1:8765/api/damage/buffs >/dev/null 2>&1; then
        systemctl reload nginx
        echo 'Roco ready: public calculator on port 80; debug console on loopback port 8765.'
        exit 0
    fi
    sleep 1
done
journalctl -u roco -n 30 --no-pager
exit 1
