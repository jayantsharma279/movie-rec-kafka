import pandas as pd
import numpy as np
from data_quality import data_quality_checks


def make_df(rows):
    return pd.DataFrame(rows, columns=["userid", "movie_id", "rating"]) 


def test_validate_good_schema():
    df = make_df([
        ("u1", "m1", 5),
        ("u2", "m2", 3),
        ("u3", "m1", 4),
    ])
    valid, issues = data_quality_checks.validate_ratings_schema(df)
    assert valid
    assert issues == []


def test_validate_bad_schema():
    df = pd.DataFrame({"userid": ["u1", None], "movie_id": ["m1", ""], "rating": [5, 6]})
    valid, issues = data_quality_checks.validate_ratings_schema(df)
    assert not valid
    # expect at least a rating out-of-range and null userid
    assert any("null" in s or ">5" in s or "empty" in s or "non-numeric" in s for s in issues)

def test_validate_wrong_datatype():
    # userid is int instead of string
    df = pd.DataFrame({
        "userid": [123, 456],
        "movie_id": ["m1", "m2"],
        "rating": [4, 5]
    })
    valid, issues = data_quality_checks.validate_ratings_schema(df)
    assert not valid
    assert any("should be string" in s for s in issues)

def test_validate_duplicates():
    df = pd.DataFrame({
        "userid": ["u1", "u1"],
        "movie_id": ["m1", "m1"],
        "rating": [4, 5]
    })
    valid, issues = data_quality_checks.validate_ratings_schema(df)
    assert not valid
    assert any("duplicate" in s for s in issues)

def test_validate_empty_df():
    df = pd.DataFrame(columns=["userid", "movie_id", "rating"])
    valid, issues = data_quality_checks.validate_ratings_schema(df)
    assert not valid
    assert any("empty" in s.lower() for s in issues)

def test_detect_no_drift():
    base = make_df([
        ("u1", "m1", 4),
        ("u2", "m2", 3),
        ("u3", "m1", 5),
        ("u4", "m3", 2),
    ])
    new = make_df([
        ("u5", "m1", 4),
        ("u6", "m2", 3),
        ("u7", "m1", 5),
        ("u8", "m3", 2),
    ])
    out = data_quality_checks.detect_rating_drift(base, new, kl_threshold=1.0, mean_diff_threshold=1.0)
    assert out["drift_flag_kl"] is False
    assert out["drift_flag_mean"] is False


def test_detect_drift_mean_change():
    base = make_df([(f"u{i}", "m1", 5) for i in range(20)])
    new = make_df([(f"u{i}", "m1", 1) for i in range(20)])
    out = data_quality_checks.detect_rating_drift(base, new, kl_threshold=0.01, mean_diff_threshold=0.5)
    assert out["drift_flag_mean"] is True
    assert out["drift_flag_kl"] is True
