#!/usr/bin/env python3
import os
import sys
from collections import defaultdict
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
RECS_FILE = str(_LOG_DIR / "telemetry_recs.log")
WATCH_FILE = str(_LOG_DIR / "watches.log")
ROLLUP_DIR = str(_ROLLUP_DIR)
OUT_CSV = str(_ROLLUP_DIR / "hit_rate_30m.csv")
OUT_CSV_VERSIONS = str(_ROLLUP_DIR / "hit_rate_30m_versions.csv")


def parse_ts(s: str):
    # handle ISO or simple formats; assume ISO with timezone present from API
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def load_recs(window_start, window_end):
    """
    Load recommendation events from telemetry_recs.log.

    Supports both old and new formats:

    Old:
      ts,route,user_id,latency_ms,rec_ids_pipe

    New:
      ts,route,user_id,latency_ms,model_version,rec_ids_pipe
    """
    recs = []
    if not os.path.exists(RECS_FILE):
        return recs

    with open(RECS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # At most 5 splits -> up to 6 fields
            parts = line.split(",", 5)

            if len(parts) < 5:
                # malformed
                continue

            ts = parse_ts(parts[0])
            if not ts or not (window_start <= ts <= window_end):
                continue

            # Old format: 5 fields
            if len(parts) == 5:
                route, uid, _lat, rec_ids_str = parts[1], parts[2], parts[3], parts[4]
                model_version = "v1"
            else:
                # New format: 6 fields
                route, uid, _lat, model_version, rec_ids_str = parts[1], parts[2], parts[3], parts[4], parts[5]

            rec_ids = rec_ids_str.split("|") if rec_ids_str else []
            recs.append((ts, route, uid, model_version, rec_ids))

    return recs


def load_watches(start_ts, end_ts):
    # watches: ts, uid, mid, minute
    watches = {}  # user_id -> list[(ts, mid)]
    if not os.path.exists(WATCH_FILE):
        return watches
    with open(WATCH_FILE, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 4:
                continue
            ts = parse_ts(parts[0])
            if not ts or ts < start_ts or ts > end_ts:
                continue
            uid, mid = parts[1], parts[2]
            watches.setdefault(uid, []).append((ts, mid))
    return watches


def main():
    now = datetime.now(timezone.utc)
    # rec window: [now-90m, now-30m]
    rec_start = now - timedelta(minutes=90)
    rec_end = now - timedelta(minutes=30)
    # we need watches up to now (but hits must be within rec_ts+30m)
    watches = load_watches(rec_start, now)

    recs = load_recs(rec_start, rec_end)

    # Overall totals
    total = hits = cold_total = cold_hits = warm_total = warm_hits = 0

    # Per-model totals
    model_stats = defaultdict(lambda: {
        "total": 0,
        "hits": 0,
        "cold_total": 0,
        "cold_hits": 0,
        "warm_total": 0,
        "warm_hits": 0,
    })

    for rec_ts, route, uid, model_version, rec_ids in recs:
        total += 1
        if route == "cold":
            cold_total += 1
        else:
            warm_total += 1

        # Per-model counters
        ms = model_stats[model_version]
        ms["total"] += 1
        if route == "cold":
            ms["cold_total"] += 1
        else:
            ms["warm_total"] += 1

        # check for any watch in [rec_ts, rec_ts+30m] whose movie is in rec_ids
        watch_deadline = rec_ts + timedelta(minutes=30)
        watched = False
        for (wts, mid) in watches.get(uid, []):
            if rec_ts <= wts <= watch_deadline and mid in rec_ids:
                watched = True
                break

        if watched:
            hits += 1
            if route == "cold":
                cold_hits += 1
            else:
                warm_hits += 1

            # per-model hits
            ms["hits"] += 1
            if route == "cold":
                ms["cold_hits"] += 1
            else:
                ms["warm_hits"] += 1

    ts_str = now.isoformat(timespec="minutes")

    # ---- Write overall rollup (existing CSV) ----
    header_needed = not os.path.exists(OUT_CSV)
    with open(OUT_CSV, "a", encoding="utf-8") as out:
        if header_needed:
            out.write(
                "ts_utc,total,hits,hit_rate_pct,"
                "cold_total,cold_hits,cold_hit_rate_pct,"
                "warm_total,warm_hits,warm_hit_rate_pct\n"
            )
        if total == 0:
            row = f"{ts_str},0,0,0.0,0,0,0.0,0,0,0.0\n"
        else:
            hr = 100.0 * hits / total
            chr = (100.0 * cold_hits / cold_total) if cold_total else 0.0
            whr = (100.0 * warm_hits / warm_total) if warm_total else 0.0
            row = (
                f"{ts_str},{total},{hits},{hr:.2f},"
                f"{cold_total},{cold_hits},{chr:.2f},"
                f"{warm_total},{warm_hits},{whr:.2f}\n"
            )
        out.write(row)

    # ---- Write per-model-version rollup ----
    header_needed_mv = not os.path.exists(OUT_CSV_VERSIONS)
    with open(OUT_CSV_VERSIONS, "a", encoding="utf-8") as out:
        if header_needed_mv:
            out.write(
                "ts_utc,model_version,total,hits,hit_rate_pct,"
                "cold_total,cold_hits,cold_hit_rate_pct,"
                "warm_total,warm_hits,warm_hit_rate_pct\n"
            )

        for mv in sorted(model_stats.keys()):
            s = model_stats[mv]
            total_m = s["total"]
            hits_m = s["hits"]
            cold_total_m = s["cold_total"]
            cold_hits_m = s["cold_hits"]
            warm_total_m = s["warm_total"]
            warm_hits_m = s["warm_hits"]

            if total_m == 0:
                hr_m = 0.0
            else:
                hr_m = 100.0 * hits_m / total_m

            chr_m = (100.0 * cold_hits_m / cold_total_m) if cold_total_m else 0.0
            whr_m = (100.0 * warm_hits_m / warm_total_m) if warm_total_m else 0.0

            row = (
                f"{ts_str},{mv},{total_m},{hits_m},{hr_m:.2f},"
                f"{cold_total_m},{cold_hits_m},{chr_m:.2f},"
                f"{warm_total_m},{warm_hits_m},{whr_m:.2f}\n"
            )
            out.write(row)

    return 0


if __name__ == "__main__":
    sys.exit(main())
