#!/usr/bin/env python3
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

LOG_DIR = os.environ.get("RECSYS_LOG_DIR", "/var/log/recsys")
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

            # Split into lines; keep the first chunk in buffer (may be partial)
            *lines, buffer = buffer.split(b"\n")

            for line in reversed(lines):
                if line:
                    yield line.decode("utf-8", errors="ignore")

        # Whatever is left in buffer is the first line
        if buffer:
            yield buffer.decode("utf-8", errors="ignore")

def parse_ts(s: str):
    s = s.strip()

    # Fix malformed "YYYY-MM-DD T..." → "YYYY-MM-DDT..."
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

    # Try fallback formats
    fallback_formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ]

    for fmt in fallback_formats:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue

    # If totally unparseable, skip and warn
    #print(f"WARNING: could not parse timestamp '{s}'")
    return None


def load_watches(start_ts, end_ts):
    """
    Load watches from watches.log between start_ts and end_ts.
    Scans from the end backwards and stops once entries are older than start_ts.
    watches.log format: ts, uid, mid, minute
    """
    movie_stats = {}  # mid -> { "total_watches": int, "unique_users": set[str] }

    if not os.path.exists(WATCH_FILE):
        return movie_stats

    for line in iter_lines_reverse(WATCH_FILE):
        parts = line.strip().split(",")
        if len(parts) < 4:
            continue

        ts = parse_ts(parts[0])
        if ts is None:
            continue

        # Going backwards in time:
        if ts < start_ts:
            break
        if ts > end_ts:
            continue

        uid, mid = parts[1], parts[2]

        # ✅ Always initialize with the same schema
        stats = movie_stats.setdefault(
            mid,
            {
                "total_watches": 0,
                "unique_users": set(),
            },
        )

        stats["total_watches"] += 1
        stats["unique_users"].add(uid)

    return movie_stats


def main():
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=7)
    window_end = now

    print(f"Scanning watches from {window_start} to {window_end}")

    movie_stats = load_watches(window_start, window_end)

    if not movie_stats:
        print("No watches found in this window.")
        return 0

    # Thresholds for suspicious "boosting" pattern
    MIN_WATCHES = 50       # needs at least this many total watches
    MAX_USERS = 5          # but from at most this many distinct users
    MIN_AVG_PER_USER = 5.0 # and avg watches per user is high

    suspicious = []

    for mid, s in movie_stats.items():
        total = s.get("total_watches", 0)
        uniq = len(s.get("unique_users", set()))

        if total == 0:
            continue

        # Very simple heuristic: few users, many watches → suspicious
        avg_watches_per_user = total / max(uniq, 1)

        # Tune these thresholds as you like
        if total >= 20 and avg_watches_per_user >= 5:
            suspicious.append((mid, total, uniq, avg_watches_per_user))

    suspicious.sort(key=lambda x: x[1], reverse=True)

    print("=== Potential poisoning candidates (top 20) ===")
    for mid, total, uniq, avg in suspicious[:20]:
        print(f"movie={mid}, total_watches={total}, unique_users={uniq}, avg_watches_per_user={avg:.2f}")

    # print("\n=== Possible Poisoning / Boosting Candidates (7 days) ===")
    # print(
    #     "Heuristic: movies with many watches but from very few distinct users, "
    #     "and high avg watches per user."
    # )
    # print(f"Thresholds: MIN_WATCHES={MIN_WATCHES}, MAX_USERS={MAX_USERS}, MIN_AVG_PER_USER={MIN_AVG_PER_USER}")
    # print("")

    if not suspicious:
        print("No movies matched the simple poisoning heuristic.")
        return 0

    print("Top suspicious movies:")
    print(
        "movie_id,total_watches,distinct_users,avg_watches_per_user,"
        "first_watch_utc,last_watch_utc,duration_hours"
    )
    for mid, total, user_count, avg_per_user, first_ts, last_ts, dur_h in suspicious[:20]:
        print(
            f"{mid},{total},{user_count},{avg_per_user:.2f},"
            f"{first_ts.isoformat(timespec='minutes')},"
            f"{last_ts.isoformat(timespec='minutes')},"
            f"{dur_h:.2f}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
