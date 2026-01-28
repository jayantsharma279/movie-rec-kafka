"""
tests/test_models.py

Unit tests for the model training and evaluation modules in scripts/models/.

Covers:
- train_svd.py   → verifies model + fallback list artifacts
- train_cf.py    → verifies CF model training and artifact creation
- eval_models.py → verifies offline evaluation metrics and CSV output
"""

import os
import pickle
import pandas as pd
import pytest
from scripts.models import train_svd, train_cf, eval_models


# SVD Model Training
def test_train_svd_artifacts():
    """
    Ensure that SVD training runs successfully and produces valid artifacts.
    """
    svd_model, top20 = train_svd.main()

    # Check model artifacts exist
    assert os.path.exists("scripts/models/svd_model.pkl"), "svd_model.pkl not created"
    assert os.path.exists("scripts/models/popular_top20.pkl"), "popular_top20.pkl not created"

    # Verify the fallback list
    assert isinstance(top20, list) and len(top20) > 0, "Top-20 fallback list should be non-empty"

    # Ensure model can be loaded
    with open("scripts/models/svd_model.pkl", "rb") as f:
        loaded_model = pickle.load(f)
    assert hasattr(loaded_model, "predict"), "Loaded SVD model must implement .predict()"


# User-User CF Model Training
def test_train_cf_artifacts():
    """
    Ensure that User-User Collaborative Filtering model training works and artifacts are produced.
    """
    cf_model = train_cf.main()

    # Check model artifact
    assert os.path.exists("scripts/models/user_cf_model.pkl"), "user_cf_model.pkl not created"

    # Ensure model can be loaded and has predict()
    with open("scripts/models/user_cf_model.pkl", "rb") as f:
        loaded_cf = pickle.load(f)
    assert hasattr(loaded_cf, "predict"), "Loaded CF model must implement .predict()"


# Offline Evaluation Results
def test_eval_models_results():
    """
    Validate that eval_models.main() returns a DataFrame with expected metrics
    and that the comparison CSV file is created.
    """
    results_df = eval_models.main()

    # Type check
    assert isinstance(results_df, pd.DataFrame), "Evaluation output must be a DataFrame"
    assert not results_df.empty, "Evaluation results DataFrame should not be empty"

    # Column check
    required_cols = {"RMSE", "MAE", "train_time_sec", "latency_ms", "size_mb"}
    assert required_cols.issubset(results_df.columns), f"Missing columns in results: {required_cols - set(results_df.columns)}"

    # Artifact check
    assert os.path.exists("scripts/models/model_comparison.csv"), "model_comparison.csv not generated"

    # Ensure both model rows exist
    assert set(results_df.index) >= {"SVD", "User-User CF"}, "Both model types should be evaluated"


# Error Handling (Optional Bonus for Coverage)
def test_eval_models_handles_missing_data(monkeypatch):
    """
    Simulate missing dataset and verify eval_models raises a clear error.
    """
    def fake_read_csv(*args, **kwargs):
        raise FileNotFoundError("Dataset not found for testing")

    monkeypatch.setattr(eval_models.pd, "read_csv", fake_read_csv)

    with pytest.raises(FileNotFoundError):
        eval_models.main()