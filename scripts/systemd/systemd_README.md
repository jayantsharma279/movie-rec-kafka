# Team 17 – systemd units & admin helpers

This folder contains the units and helpers used to keep our recsys, telemetry, and Kafka tunnel running.

## Units

### `kafka-tunnel.service`
Maintains an SSH tunnel from `localhost:9092` on the VM to `128.2.220.241:9092` (course Kafka).
- **Requires** private key at `/home/team17/.ssh/tunnel_kafka` (chmod 600).
- Install/enable:
  ```bash
  sudo install -m 0644 scripts/systemd/kafka-tunnel.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now kafka-tunnel.service
  ```
- Verify: `ss -ltnp | grep :9092`, `systemctl status kafka-tunnel`

### `recsys.service`
Gunicorn + Flask app server for `/recommend/<user_id>`.
- Already installed at `/etc/systemd/system/recsys.service`.
- Common ops:
  ```bash
  sudo systemctl restart recsys
  sudo systemctl status recsys --no-pager
  sudo journalctl -u recsys -f
  ```

### `recsys-watch-consumer.service`
Kafka consumer that writes first-minute watch events to `/var/log/recsys/watch_starts.log`.
- Reads environment from `/etc/recsys/env`:
  ```bash
  KAFKA_BROKERS=localhost:9092
  KAFKA_TOPIC_LOGS=movielog17
  RECSYS_LOG_DIR=/var/log/recsys
  ```
- Install/enable:
  ```bash
  sudo install -m 0644 scripts/systemd/recsys-watch-consumer.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now recsys-watch-consumer.service
  ```
- Verify:
  ```bash
  sudo systemctl status recsys-watch-consumer --no-pager
  tail -f /var/log/recsys/watch_starts.log
  ```

### `telemetry-coldwarm.service` + `telemetry-coldwarm.timer`
Hourly rollup of cold/warm share into `/var/log/recsys/rollups/cold_warm_share.csv`.
- Install/enable:
  ```bash
  sudo install -m 0644 scripts/systemd/telemetry-coldwarm.service /etc/systemd/system/
  sudo install -m 0644 scripts/systemd/telemetry-coldwarm.timer   /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now telemetry-coldwarm.timer
  ```
- Manual run: `sudo systemctl start telemetry-coldwarm.service`
- Verify:
  ```bash
  systemctl list-timers --all | grep telemetry-coldwarm
  tail -n 5 /var/log/recsys/rollups/cold_warm_share.csv
  ```

### `telemetry-hitrate.service` + `telemetry-hitrate.timer`
Hourly computation of “watch within 30 minutes” hit rate into `/var/log/recsys/rollups/hit_rate_30m.csv`.
- Install/enable:
  ```bash
  sudo install -m 0644 scripts/systemd/telemetry-hitrate.service /etc/systemd/system/
  sudo install -m 0644 scripts/systemd/telemetry-hitrate.timer   /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now telemetry-hitrate.timer
  ```
- Manual run: `sudo systemctl start telemetry-hitrate.service`
- Verify:
  ```bash
  systemctl list-timers --all | grep telemetry-hitrate
  tail -n 5 /var/log/recsys/rollups/hit_rate_30m.csv
  ```

## Admin helper

### `recsys-admin.sh`
Convenience script to restart and check status of all services/timers.
- Make executable:
  ```bash
  chmod +x scripts/systemd/recsys-admin.sh
  sudo install -m 0755 scripts/systemd/recsys-admin.sh /usr/local/bin/recsys-admin
  ```
- Usage:
  ```bash
  sudo scripts/systemd/recsys-admin.sh restart
  sudo scripts/systemd/recsys-admin.sh status
  ```

## Environment & logs

- Environment for consumers: `/etc/recsys/env`
- Logs:
  - `/var/log/recsys/telemetry_cw.log`
  - `/var/log/recsys/telemetry_recs.log`
  - `/var/log/recsys/watch_starts.log`
  - Rollups in `/var/log/recsys/rollups/`

## Optional: log rotation (recommended)

Create `/etc/logrotate.d/recsys`:
```conf
/var/log/recsys/*.log {
  weekly
  rotate 8
  compress
  missingok
  notifempty
  create 0644 team17 team17
}
```
Test with: `sudo logrotate -d /etc/logrotate.conf`
