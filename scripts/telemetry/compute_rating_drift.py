#!/usr/bin/env python3
"""
Compute rating distribution drift between:
- baseline training ratings: dataset/movie_ratings.csv
- live ratings:              $RECSYS_LOG_DIR/ratings.log (default /var/log/recsys/ratings.log)

Writes a single rollup row to:
    $RECSYS_LOG_DIR/rollups/rating_drift.csv

Columns:
    ts_utc
    total_ratings
    kl_divergence
    mean_diff
    drift_flag_kl
    drift_flag_mean
    frac_movies_big_count_change
    big_count_change_flag
    kl_threshold
    mean_diff_threshold
"""

import os
import sys
import csv
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pandas as pd

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))

from data_quality import data_quality_checks


def load_baseline_df(repo_root: Path) -> pd.DataFrame:
    """
    Load the baseline ratings used for training.

    Expected path: <repo_root>/dataset/movie_ratings.csv

    Handles common column name variants:
      - userId / user_id
      - movieId / movie_id
      - rating
    """
    baseline_path = repo_root / "dataset" / "movie_ratings.csv"
    if not baseline_path.exists():
        raise FileNotFoundError(f"Baseline ratings CSV not found at {baseline_path}")

    df = pd.read_csv(baseline_path)

    # Normalize column names
    rename_map = {}
    if "userId" in df.columns:
        rename_map["userId"] = "user_id"
    if "movieId" in df.columns:
        rename_map["movieId"] = "movie_id"
    if "UserID" in df.columns:
        rename_map["UserID"] = "user_id"
    if "MovieID" in df.columns:
        rename_map["MovieID"] = "movie_id"

    df = df.rename(columns=rename_map)

    # Ensure required columns exist
    if "rating" not in df.columns:
        raise ValueError("Baseline ratings CSV must contain a 'rating' column")
    if "movie_id" not in df.columns:
        # not strictly required for KL/mean, but needed for per-movie stats
        df["movie_id"] = None
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df = df.dropna(subset=["rating"])

    return df


def load_live_ratings(log_dir: Path) -> pd.DataFrame:
    """
    Load live ratings from ratings.log.

    Format (one line per rating):
        ts_utc,user_id,movie_id,rating

    This is produced by the extended watch-consumer script.
    """
    ratings_log = log_dir / "ratings.log"
    if not ratings_log.exists():
        # No live ratings yet → return empty
        return pd.DataFrame(columns=["ts", "user_id", "movie_id", "rating"])

    # There is no header; define columns explicitly
    df = pd.read_csv(
        ratings_log,
        names=["ts", "user_id", "movie_id", "rating"],
        dtype={"ts": str, "user_id": str, "movie_id": str},
        float_precision="high",
    )

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=1)

    df["ts"] = pd.to_datetime(df["ts"], errors="coerce", utc=True)
    df = df.dropna(subset=["ts"])
    df = df[df["ts"] >= cutoff]

    # Normalize column names to match drift function expectations
    df = df.rename(columns={"movie_id": "movie_id", "rating": "rating"})

    # Ensure correct types
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")

    return df


def append_rollup_row(rollup_path: Path, metrics: dict, total_ratings: int) -> None:
    """
    Append a single row with the drift metrics to rating_drift.csv.
    Creates file with header if it does not exist.
    """
    rollup_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    kl = metrics.get("kl_divergence")
    mean_diff = metrics.get("mean_diff")
    frac_big = metrics.get("frac_movies_big_count_change", float("nan"))
    big_flag = metrics.get("big_count_change_flag", False)
    thresholds = metrics.get("thresholds", {}) or {}
    kl_thr = thresholds.get("kl_threshold")
    mean_thr = thresholds.get("mean_diff_threshold")

    row = {
        "ts_utc": now,
        "total_ratings": int(total_ratings),
        "kl_divergence": kl,
        "mean_diff": mean_diff,
        "drift_flag_kl": int(bool(metrics.get("drift_flag_kl", False))),
        "drift_flag_mean": int(bool(metrics.get("drift_flag_mean", False))),
        "frac_movies_big_count_change": frac_big,
        "big_count_change_flag": int(bool(big_flag)),
        "kl_threshold": kl_thr,
        "mean_diff_threshold": mean_thr,
    }

    header = list(row.keys())
    file_exists = rollup_path.exists()

    with rollup_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def main() -> int:
    # Repo root: .../shawshank-prediction-mlip-project
    repo_root = Path(__file__).resolve().parents[2]

    # Logs dir: RECSYS_LOG_DIR or /var/log/recsys
    log_dir = Path(os.environ.get("RECSYS_LOG_DIR", "/var/log/recsys"))

    # Rollup target
    rollup_path = log_dir / "rollups" / "rating_drift.csv"

    # 1) Load baseline
    try:
        baseline_df = load_baseline_df(repo_root)
    except Exception as e:
        print(f"[rating_drift] Failed to load baseline ratings: {e}", file=sys.stderr)
        return 1

    # 2) Load live ratings
    live_df = load_live_ratings(log_dir)
    total_live = len(live_df)

    if total_live == 0:
        # No ratings yet → append a row with NaNs / no drift, or simply no-op.
        # Here we choose to no-op to avoid cluttering the CSV with empty stats.
        print("[rating_drift] No live ratings found; skipping rollup.", file=sys.stderr)
        return 0

    # For drift we only really need rating + movie_id columns
    # but we pass full DFS so the function can compute per-movie counts.
    try:
        metrics = data_quality_checks.detect_rating_drift(
            baseline_df,
            live_df,
            # you can tune these thresholds later if needed
            kl_threshold=0.2,
            mean_diff_threshold=0.25,
        )
    except Exception as e:
        print(f"[rating_drift] Error computing drift metrics: {e}", file=sys.stderr)
        return 1

    # 3) Append rollup
    try:
        append_rollup_row(rollup_path, metrics, total_ratings=total_live)
    except Exception as e:
        print(f"[rating_drift] Failed to write rollup CSV: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
