"""
Automated retraining entry point for the Movie Recommendation System.

Responsibilities:
1. Optional: pull fresh ratings from Kafka into ``dataset/``.
2. Retrain the Surprise SVD model using ``scripts.models.train_svd``.
3. Persist versioned artifacts (model + fallback list) with timestamps.
4. Maintain provenance metadata (model version, git SHA, dataset fingerprint details).
5. Update the "active" artifacts consumed by the Flask inference service.

This script is invoked by both local cron/systemd timers and the container/K8s
CronJob. Keep it dependency-free beyond what is already in requirements.txt.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import joblib
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
import sys
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.models.train_svd import main as train_svd_main
from scripts.models.convert_log import main as convert_log_to_csv

DATA_DIR = ROOT_DIR / "dataset"
DEFAULT_DATASET = DATA_DIR / "movie_ratings_val.csv"
MODEL_DIR = ROOT_DIR / "scripts" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
METADATA_FILE = MODEL_DIR / "model_metadata.json"
ACTIVE_MODEL_FILE = MODEL_DIR / "svd_model.pkl"
ACTIVE_POP_FILE = MODEL_DIR / "popular_top20.pkl"
ACTIVE_METADATA_FILE = MODEL_DIR / "active_model.json"


def run_cmd(cmd: list[str]) -> str:
    try:
        return (
            subprocess.check_output(cmd, cwd=ROOT_DIR, stderr=subprocess.DEVNULL)
            .decode("utf-8")
            .strip()
        )
    except Exception:
        return "unknown"


def current_git_sha() -> str:
    return run_cmd(["git", "rev-parse", "HEAD"])


def compute_dataset_metadata(csv_path: Path) -> Dict[str, object]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Dataset not found: {csv_path}")

    try:
        df = pd.read_csv(csv_path)
        rows = len(df)
    except Exception:
        rows = sum(1 for _ in open(csv_path, "r", encoding="utf-8")) - 1  # drop header

    rel_path = os.path.relpath(csv_path, ROOT_DIR)
    stat = csv_path.stat()
    modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds")
    version_id = f"{os.path.basename(csv_path)}@{int(stat.st_mtime)}"

    return {
        "path": rel_path,
        "rows": rows,
        "size_bytes": stat.st_size,
        "modified_at": modified,
        "version_id": version_id,
    }


def load_metadata_history() -> list:
    if METADATA_FILE.exists():
        with open(METADATA_FILE, "r", encoding="utf-8") as handle:
            try:
                return json.load(handle)
            except json.JSONDecodeError:
                return []
    return []


def append_metadata(entry: Dict[str, object]) -> None:
    history = load_metadata_history()
    history.append(entry)
    with open(METADATA_FILE, "w", encoding="utf-8") as handle:
        json.dump(history, handle, indent=2)


def publish_active_artifacts(model_path: Path, pop_path: Path, metadata: Dict[str, object]) -> None:
    shutil.copy2(model_path, ACTIVE_MODEL_FILE)
    shutil.copy2(pop_path, ACTIVE_POP_FILE)

    payload = {
        **metadata,
        "active_model_path": os.path.relpath(ACTIVE_MODEL_FILE, ROOT_DIR),
        "active_popular_path": os.path.relpath(ACTIVE_POP_FILE, ROOT_DIR),
        "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    with open(ACTIVE_METADATA_FILE, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    print(f"[publish] Active model updated → {ACTIVE_MODEL_FILE.name}")


def retrain_model(data_path: Path, data_source: str, note: Optional[str] = None) -> Dict[str, object]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    version = f"svd_model_{timestamp}"
    model_path = MODEL_DIR / f"{version}.pkl"
    pop_path = MODEL_DIR / f"popular_top20_{timestamp}.pkl"

    data_path = convert_log_to_csv()

    print(f"[train] Starting retraining at {timestamp}")
    print(f"[train] Using dataset: {data_path}")

    model, top20 = train_svd_main(str(data_path))
    joblib.dump(model, model_path)
    joblib.dump(top20, pop_path)

    stats = compute_dataset_metadata(data_path)
    git_sha = current_git_sha()

    metadata_entry = {
        "model_version": version,
        "model_artifact": os.path.relpath(model_path, ROOT_DIR),
        "fallback_artifact": os.path.relpath(pop_path, ROOT_DIR),
        "trained_on": timestamp,
        "pipeline_git_sha": git_sha,
        "data": stats,
        "data_source": data_source,
        "note": note or "",
    }

    append_metadata(metadata_entry)
    publish_active_artifacts(model_path, pop_path, metadata_entry)

    print(f"[train] Completed retraining → {version}")
    return metadata_entry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automated retraining entry point")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Path to ratings CSV. Defaults to dataset/movie_ratings.csv",
    )
    parser.add_argument(
        "--pull-latest",
        action="store_true",
        help="Fetch the latest ratings via Kafka before training.",
    )
    parser.add_argument(
        "--output-name",
        default="new_dataset.csv",
        help="Filename for the fetched dataset (when --pull-latest is set).",
    )
    parser.add_argument(
        "--note",
        default="",
        help="Optional note stored inside the metadata entry.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.pull_latest:
        data_path= args.output_name
        data_source = "kafka"
    else:
        data_path = args.dataset
        data_source = "static"

    retrain_model(data_path=data_path, data_source=data_source, note=args.note)


if __name__ == "__main__":
    main()
