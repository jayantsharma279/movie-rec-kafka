"""
Utilities for schema validation and simple drift detection for the movie ratings
dataset used in the project.

"""
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
from scipy.stats import entropy

REQUIRED_COLUMNS = {"userid", "movie_id", "rating"}

def validate_ratings_schema(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """Validate that ratings DataFrame contains expected columns and types.
    """
    issues: List[str] = []

    if not isinstance(df, pd.DataFrame):
        issues.append("Input is not a pandas DataFrame")
        return False, issues
    
    if df.empty:
        issues.append("Dataset is empty (no rows to process)")
        return False, issues

    cols = set(df.columns)
    missing = REQUIRED_COLUMNS - cols
    if missing:
        issues.append(f"Missing required columns: {sorted(list(missing))}")

    # Check for nulls in required columns
    for c in REQUIRED_COLUMNS & cols:
        nnull = int(df[c].isna().sum())
        if nnull > 0:
            issues.append(f"Column '{c}' has {nnull} null values")

    # Check rating numeric and in 1..5
    if "rating" in cols:
        if not pd.api.types.is_numeric_dtype(df["rating"]):
            issues.append("Column 'rating' is not numeric")
        else:
            # coerce to numeric view for checking
            r = pd.to_numeric(df["rating"], errors="coerce")
            low = (r < 1).sum()
            high = (r > 5).sum()
            nan = r.isna().sum()
            if nan > 0:
                issues.append(f"Column 'rating' has {int(nan)} non-numeric values")
            if low > 0 or high > 0:
                issues.append(f"Column 'rating' has {int(low)} <1 and {int(high)} >5 values")

    for key in ("userid", "movie_id"):
        if key in cols:
            # Check datatype (should be string)
            if not pd.api.types.is_string_dtype(df[key]):
                issues.append(f"Column '{key}' should be string type, found {df[key].dtype}")
                # Cast to string to safely perform next check
                df[key] = df[key].astype(str)

            # Check for empty or whitespace-only entries
            empties = int((df[key].astype(str).str.strip() == "").sum())
            if empties > 0:
                issues.append(f"Column '{key}' has {empties} empty strings")
    
    # Check for duplicate (userid, movie_id) pairs
    if all(col in df.columns for col in ["userid", "movie_id"]):
        dupes = df.duplicated(subset=["userid", "movie_id"]).sum()
        if dupes > 0:
            issues.append(f"Found {dupes} duplicate (userid, movie_id) pairs")


    valid = len(issues) == 0
    return valid, issues



def detect_rating_drift(baseline_df: pd.DataFrame, new_df: pd.DataFrame, *,
                        kl_threshold: float = 0.2, mean_diff_threshold: float = 0.25) -> Dict:
    """Detect strong drift between baseline and new rating datasets.

    Returns a dictionary with computed statistics and booleans indicating whether
    thresholds were exceeded. Uses KL divergence of rating distributions (discrete
    ratings 1-5) and absolute difference in mean rating.

    """
    out = {}

    # Work on copies
    b = baseline_df.copy()
    n = new_df.copy()

    # Ratings arrays
    if "rating" not in b.columns or "rating" not in n.columns:
        raise ValueError("Both dataframes must contain 'rating' column")

    # Use discrete bins for ratings 1..5
    b_r = b["rating"].dropna().astype(float)
    n_r = n["rating"].dropna().astype(float)

    # Build distribution vectors over ratings 1..5
    ratings = np.array([1, 2, 3, 4, 5])
    b_counts = np.array([(b_r == r).sum() for r in ratings], dtype=float)
    n_counts = np.array([(n_r == r).sum() for r in ratings], dtype=float)
    # add small smoothing to avoid zeros in KL
    eps = 1e-8
    b_probs = (b_counts + eps) / (b_counts.sum() + eps * len(b_counts))
    n_probs = (n_counts + eps) / (n_counts.sum() + eps * len(n_counts))

    kl = float(entropy(b_probs, n_probs))
    mean_diff = float(abs(b_r.mean() - n_r.mean())) if len(b_r) and len(n_r) else float('nan')

    out["kl_divergence"] = kl
    out["mean_diff"] = mean_diff
    out["thresholds"] = {
        "kl_threshold": kl_threshold,
        "mean_diff_threshold": mean_diff_threshold,
    }
    out["drift_flag_kl"] = kl > kl_threshold
    out["drift_flag_mean"] = mean_diff > mean_diff_threshold

    # Additionally check change in per-movie rating counts to flag sudden volume changes
    if "movie_id" in b.columns and "movie_id" in n.columns:
        b_counts_per_movie = b.groupby('movie_id').size()
        n_counts_per_movie = n.groupby('movie_id').size()
        merged = pd.concat([b_counts_per_movie, n_counts_per_movie], axis=1, keys=['b', 'n']).fillna(0)
        merged['pct_change'] = 0.0
        # avoid divide by zero
        merged['pct_change'] = merged.apply(lambda row: float('inf') if row['b']==0 and row['n']>0 else (abs(row['n']-row['b'])/max(row['b'],1)), axis=1)
        # fraction of movies with huge change (>100% increase or decrease)
        big_changes = (merged['pct_change'] > 1.0).sum()
        frac_big = big_changes / max(1, len(merged))
        out['frac_movies_big_count_change'] = float(frac_big)
        out['big_count_change_flag'] = frac_big > 0.1  # if >10% of movies changed a lot

    return out

