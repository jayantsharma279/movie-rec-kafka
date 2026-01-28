import pandas as pd
from scipy.stats import ttest_ind
import os
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
OUT_CSV_VERSIONS = str(_ROLLUP_DIR / "hit_rate_30m_versions.csv")
OUT_TTEST_CSV = str(_ROLLUP_DIR / "ttest_results.csv")

df = pd.read_csv(OUT_CSV_VERSIONS)

results = []

# get all model versions
models = df["model_version"].unique()

# build event-level data per model
model_events = {}

for model in models:
    rows = df[df["model_version"] == model]

    hits = rows["hits"].sum()
    total = rows["total"].sum()
    misses = total - hits

    # create binary array
    events = [1] * hits + [0] * misses
    model_events[model] = events

# pairwise t-tests
for i in range(len(models)):
    for j in range(i + 1, len(models)):
        m1, m2 = models[i], models[j]

        t_stat, p_val = ttest_ind(model_events[m1], model_events[m2], equal_var=False)

        results.append({
            "model_A": m1,
            "model_B": m2,
            "t_stat": t_stat,
            "p_value": p_val,
            "significant": p_val < 0.05
        })

pd.DataFrame(results).to_csv(OUT_TTEST_CSV, index=False)
