#!/usr/bin/env bash
# Simple admin helper for Team 17 services.
# Usage:
#   sudo scripts/systemd/recsys-admin.sh restart   # install units + restart all
#   sudo scripts/systemd/recsys-admin.sh status    # show status
#   sudo scripts/systemd/recsys-admin.sh reload    # daemon-reload + status

set -euo pipefail

# Directory this script lives in (e.g. .../scripts/systemd)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_SRC="$SCRIPT_DIR"
SYSTEMD_DIR="/etc/systemd/system"

UNITS=(
  "kafka-tunnel.service"
  "recsys.service"
  "recsys-watch-consumer.service"
  "telemetry-rating-drift.service"
  "telemetry-rating-drift.timer"
  "telemetry-coldwarm.service"
  "telemetry-coldwarm.timer"
  "telemetry-hitrate.service"
  "telemetry-hitrate.timer"
)

action="${1:-status}"

case "$action" in
  restart)
    echo "Installing latest systemd unit files from $UNIT_SRC to $SYSTEMD_DIR ..."

    install -m 0644 "$UNIT_SRC/telemetry-coldwarm.service"        "$SYSTEMD_DIR/"
    install -m 0644 "$UNIT_SRC/telemetry-hitrate.service"         "$SYSTEMD_DIR/"
    install -m 0644 "$UNIT_SRC/telemetry-rating-drift.service"    "$SYSTEMD_DIR/"
    install -m 0644 "$UNIT_SRC/recsys-watch-consumer.service"     "$SYSTEMD_DIR/"
    install -m 0644 "$UNIT_SRC/kafka-tunnel.service"              "$SYSTEMD_DIR/"

    systemctl daemon-reload

    # Enable & start timers
    systemctl enable --now telemetry-coldwarm.timer telemetry-hitrate.timer telemetry-rating-drift.timer || true

    # Restart core services
    systemctl restart kafka-tunnel.service recsys.service recsys-watch-consumer.service
    ;;
  reload)
    systemctl daemon-reload
    ;;
  status)
    # just fall through to status printout
    ;;
  *)
    echo "Usage: $0 {restart|status|reload}" >&2
    exit 2
    ;;
esac

echo
echo "=== Service/Timer Status ==="
for u in "${UNITS[@]}"; do
  echo "-- $u"
  systemctl --no-pager --full status "$u" | sed -n '1,12p' || true
  echo
done

echo "=== Timers ==="
systemctl list-timers --all | grep -E 'telemetry-(coldwarm|hitrate|rating-drift)\.timer' || true

echo "=== Log Heads ==="
/usr/bin/tail -n 3 /var/log/recsys/telemetry_cw.log      2>/dev/null || true
/usr/bin/tail -n 3 /var/log/recsys/telemetry_recs.log    2>/dev/null || true
/usr/bin/tail -n 3 /var/log/recsys/watch_starts.log      2>/dev/null || true
/usr/bin/tail -n 3 /var/log/recsys/ratings.log           2>/dev/null || true
/usr/bin/tail -n 3 /var/log/recsys/rollups/hit_rate_30m.csv    2>/dev/null || true
/usr/bin/tail -n 3 /var/log/recsys/rollups/cold_warm_share.csv 2>/dev/null || true
/usr/bin/tail -n 3 /var/log/recsys/rollups/rating_drift.csv    2>/dev/null || true
