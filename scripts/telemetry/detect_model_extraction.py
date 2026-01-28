#!/usr/bin/env python3
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

LOG_DIR = os.environ.get("RECSYS_LOG_DIR", "/var/log/recsys")
RECS_FILE = os.path.join(LOG_DIR, "telemetry_recs.log")
WATCH_FILE = os.path.join(LOG_DIR, "watches.log")


def iter_lines_reverse(path, chunk_size=8192):
    """Yield lines from a file in reverse order (last line first)."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        position = f.tell()
        buffer = b""

        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            f.seek(position)
            chunk = f.read(read_size)
            buffer = chunk + buffer

            *lines, buffer = buffer.split(b"\n")

            for line in reversed(lines):
                if line:
                    yield line.decode("utf-8", errors="ignore")

        if buffer:
            yield buffer.decode("utf-8", errors="ignore")


def parse_ts(s: str):
    s = s.strip()

    # Fix malformed "YYYY-MM-DD T..." -> "YYYY-MM-DDT..."
    if " T" in s:
        s = s.replace(" T", "T")

    # Try ISO first
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    # Fallback formats
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue

    return None


def load_recs(window_start, window_end):
    """
    Load recommendation events from telemetry_recs.log for [window_start, window_end].
    Scans the file from the end backwards and stops once entries are older than window_start.

    Supports both formats:
      old: ts,route,user_id,latency_ms,rec_ids_pipe
      new: ts,route,user_id,latency_ms,model_version,rec_ids_pipe
    """
    recs = []
    if not os.path.exists(RECS_FILE):
        return recs

    for line in iter_lines_reverse(RECS_FILE):
        line = line.strip()
        if not line:
            continue

        parts = line.split(",", 5)
        if len(parts) < 5:
            continue

        ts = parse_ts(parts[0])
        if ts is None:
            continue

        # Going backwards in time
        if ts < window_start:
            break
        if ts > window_end:
            continue

        if len(parts) == 5:
            # Old format
            route, uid, _lat, rec_ids_str = parts[1], parts[2], parts[3], parts[4]
            model_version = "legacy"
        else:
            # New format
            route, uid, _lat, model_version, rec_ids_str = (
                parts[1],
                parts[2],
                parts[3],
                parts[4],
                parts[5],
            )

        rec_ids = rec_ids_str.split("|") if rec_ids_str else []
        recs.append((ts, route, uid, model_version, rec_ids))

    return recs


def load_watches(window_start, window_end):
    """
    Load watches from watches.log between window_start and window_end.
    Format: ts,uid,mid,minute

    Scans from the end backwards and stops once entries are older than window_start.
    """
    watches = defaultdict(list)  # uid -> list[(ts, mid)]
    if not os.path.exists(WATCH_FILE):
        return watches

    for line in iter_lines_reverse(WATCH_FILE):
        parts = line.strip().split(",")
        if len(parts) < 4:
            continue

        ts = parse_ts(parts[0])
        if ts is None:
            continue

        # Going backwards in time
        if ts < window_start:
            break
        if ts > window_end:
            continue

        uid, mid = parts[1], parts[2]
        watches[uid].append((ts, mid))

    return watches


def main():
    now = datetime.now(timezone.utc)
    # Look at the last 7 days of activity
    window_start = now - timedelta(days=7)
    window_end = now

    print(f"Scanning recs & watches from {window_start} to {window_end}")

    recs = load_recs(window_start, window_end)
    watches = load_watches(window_start, window_end)

    if not recs:
        print("No recs found in this window.")
        return 0

    user_stats = defaultdict(lambda: {"total": 0, "hits": 0})
    total = 0
    hits = 0

    for rec_ts, route, uid, model_version, rec_ids in recs:
        total += 1
        user_stats[uid]["total"] += 1

        watch_deadline = rec_ts + timedelta(minutes=30)
        watched = False
        for wts, mid in watches.get(uid, []):
            if rec_ts <= wts <= watch_deadline and mid in rec_ids:
                watched = True
                break

        if watched:
            hits += 1
            user_stats[uid]["hits"] += 1

    global_hr = 100.0 * hits / total if total else 0.0

    singleton_total = singleton_hits = 0
    multi_total = multi_hits = 0
    singleton_uids = []
    multi_uids = []

    for uid, s in user_stats.items():
        if s["total"] == 1:
            singleton_total += s["total"]
            singleton_hits += s["hits"]
            singleton_uids.append(uid)
        else:
            multi_total += s["total"]
            multi_hits += s["hits"]
            multi_uids.append(uid)

    singleton_hr = 100.0 * singleton_hits / singleton_total if singleton_total else 0.0
    multi_hr = 100.0 * multi_hits / multi_total if multi_total else 0.0

    print("\n=== Model Extraction / Probing via Hit Rate Cohorts (last 7 days) ===")
    print(f"Total recs: {total}")
    print(f"Global hit rate: {global_hr:.2f}%\n")
    print(
        f"Singleton users (exactly 1 rec): {len(singleton_uids)} users, "
        f"{singleton_total} recs, hit rate {singleton_hr:.2f}%"
    )
    print(
        f"Multi-request users (>=2 recs): {len(multi_uids)} users, "
        f"{multi_total} recs, hit rate {multi_hr:.2f}%"
    )

    # Heuristic thresholds – adjust as needed for your report
    THRESH_GLOBAL_OK = 40.0     # expected 'normal-ish' global HR
    THRESH_SINGLETON_LOW = 20.0 # suspiciously low singleton HR
    MIN_SINGLETON_RECS = 100    # avoid tiny-sample noise

    if (
        global_hr >= THRESH_GLOBAL_OK
        and singleton_total >= MIN_SINGLETON_RECS
        and singleton_hr <= THRESH_SINGLETON_LOW
    ):
        print("\n>> POTENTIAL PROBING DETECTED:")
        print("   - Global hit rate is reasonably high.")
        print("   - Singleton users have very low hit rate.")
        print("   - This matches a pattern of many one-off synthetic queries.")
    else:
        print("\n>> No strong evidence of probing under this simple heuristic.")
       

    return 0


if __name__ == "__main__":
    sys.exit(main())
