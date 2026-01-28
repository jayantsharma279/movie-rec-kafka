#!/usr/bin/env python3
"""
Scan the last hour of the telemetry log and append a row with cold/warm percentages
into the rollup CSV.

Input line schema (CSV):
ts_utc,route,user_id,latency_ms
e.g. 2025-10-23T15:20:31+00:00,warm,12345,10,2.341,svd-1
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _resolve_log_dirs() -> tuple[Path, Path]:
    base = Path(os.environ.get("RECSYS_LOG_DIR", "/var/log/recsys")).expanduser()
    rollups = base / "rollups"
    try:
        rollups.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        fallback = Path.cwd() / "tmp" / "recsys_logs"
        rollups = fallback / "rollups"
        rollups.mkdir(parents=True, exist_ok=True)
        os.environ["RECSYS_LOG_DIR"] = str(fallback)
        base = fallback
    return base, rollups


_LOG_DIR, _ROLLUP_DIR = _resolve_log_dirs()
LOG_DIR = str(_LOG_DIR)
LOG_FILE = str(_LOG_DIR / "telemetry_cw.log")
ROLLUP_DIR = str(_ROLLUP_DIR)
OUT_CSV = str(_ROLLUP_DIR / "cold_warm_share.csv")

def within_last_hour(ts_str: str, now: datetime) -> bool:
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except Exception:
        return False
    return now - timedelta(hours=1) <= ts <= now

def main():
    now = datetime.now(timezone.utc)

    cold = warm = 0
    sampled = 0

    if not os.path.exists(LOG_FILE):
        print("[rollup] no telemetry.log yet")
        return 0
    # read only the last ~10MB to avoid huge scans:
    with open(LOG_FILE, "rb") as fb:
        try:
            fb.seek(-10_000_000, os.SEEK_END)
        except OSError:
            pass
        tail = fb.read().decode("utf-8", errors="ignore").splitlines()

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "," not in line:
                continue
            # ts, route, user_id, k, latency_ms, model_version
            parts = line.split(",")
            if len(parts) < 4:
                continue
            ts_str, route = parts[0], parts[1]
            if not within_last_hour(ts_str, now):
                continue
            sampled += 1
            if route == "cold":
                cold += 1
            elif route == "warm":
                warm += 1

    if sampled == 0:
        # Still append a row so your time series has continuity
        row = f'{now.isoformat(timespec="minutes")},0,0,0.0,0.0\n'
    else:
        cold_share = 100.0 * cold / sampled
        warm_share = 100.0 * warm / sampled
        row = f'{now.isoformat(timespec="minutes")},{cold},{warm},{cold_share:.2f},{warm_share:.2f}\n'

    header_needed = not os.path.exists(OUT_CSV)
    with open(OUT_CSV, "a", encoding="utf-8") as out:
        if header_needed:
            out.write("ts_utc,cold_count,warm_count,cold_share_pct,warm_share_pct\n")
        out.write(row)

    return 0

if __name__ == "__main__":
    sys.exit(main())
