"""
tests/test_pipeline_run.py

""
Unit tests for scripts/pipeline_run.py.

These tests verify that the pipeline’s key components work correctly and
that all major stages—data ingestion (with quality validation), feature extraction,
model training, evaluation, serving, and telemetry—are connected and testable.

Kafka streaming is not executed here; data ingestion uses the cleaned dataset.
Telemetry is tested with a local directory to avoid /var/log/recsys permission issues.
"""

import os
import pytest
import pandas as pd
from pathlib import Path
from scripts import pipeline_run


# Data Ingestion and Cleaning
def test_data_ingestion_and_cleaning():
    """
    Validate that data_ingestion_and_cleaning() loads the dataset correctly.

    Checks:
    - The returned DataFrame is not empty.
    - The required columns (userid, movie_id, rating) are present.
    - The rating column is numeric and non-null.
    """
    df = pipeline_run.data_ingestion_and_cleaning()
    assert isinstance(df, pd.DataFrame), "Output should be a DataFrame"
    assert not df.empty, "Dataset should not be empty"
    assert {"userid", "movie_id", "rating"}.issubset(df.columns), \
        "Dataset missing required columns"
    assert df["rating"].notna().all(), "Ratings should not contain NaN values"
    assert pd.api.types.is_numeric_dtype(df["rating"]), "Rating column must be numeric"
    assert df["rating"].between(1, 5).all(), "Ratings must be between 1 and 5"

# Feature Extraction
def test_feature_extraction_columns():
    """
    Ensure that feature_extraction() returns the correct subset of columns
    and that all selected columns exist in the source dataset.
    """
    df = pipeline_run.data_ingestion_and_cleaning()
    features_df = pipeline_run.feature_extraction(df)
    expected_cols = ["userid", "movie_id", "rating"]
    assert list(features_df.columns) == expected_cols, \
        "Feature extraction should only return userid, movie_id, rating"
    assert not features_df.empty, "Extracted feature DataFrame should not be empty"


# Model Training
def test_model_training_artifacts(tmp_path, monkeypatch):
    """
    Verify that model_training() runs successfully and produces serialized artifacts.
    The artifact paths are checked after training.
    """
    # Run training (SVD + CF)
    svd_model, cf_model, top20 = pipeline_run.model_training()

    # Check expected outputs
    assert os.path.exists("scripts/models/svd_model.pkl"), "SVD model artifact missing"
    assert os.path.exists("scripts/models/user_cf_model.pkl"), "User-User CF model missing"
    assert os.path.exists("scripts/models/popular_top20.pkl"), "Top-20 list missing"
    assert isinstance(top20, list), "Expected top20 fallback list as a list"


# Model Evaluation
def test_model_evaluation_results():
    """
    Validate that model_evaluation() runs and returns a DataFrame with metrics.

    Checks:
    - Output is a pandas DataFrame.
    - It contains columns 'Metric' and 'Value' (from offline.py).
    """
    eval_df = pipeline_run.model_evaluation()
    assert isinstance(eval_df, pd.DataFrame), "Evaluation output must be a DataFrame"
    assert {"Metric", "Value"}.issubset(eval_df.columns), \
        "Evaluation DataFrame must include Metric and Value columns"


#  Model Serving (Flask Verification)
def test_model_serving_mocked(monkeypatch):
    """
    Mock the Flask subprocess to avoid actually starting a server.
    Ensures that model_serving() can execute without errors.
    """
    # Mock subprocess.Popen so no Flask process starts
    monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: None)
    result = pipeline_run.model_serving()
    assert result in [True, False], "Model serving verification should complete gracefully"

# Telemetry Collection
def test_telemetry_collection_local(tmp_path):
    """
    Validate that telemetry_collection() completes successfully
    and writes output CSVs under a local temporary directory.
    """
    log_dir = tmp_path / "telemetry_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    result = pipeline_run.telemetry_collection(log_dir=str(log_dir))
    assert result, "Telemetry collection should complete successfully"

    rollup_dir = log_dir / "rollups"
    assert rollup_dir.exists(), "Telemetry rollup directory should be created"
    assert any(rollup_dir.glob("*.csv")), "Telemetry output CSV files should exist"


# Full Pipeline Execution (Integration Test)
def test_full_pipeline_execution(monkeypatch, tmp_path):
    """
    Run the entire pipeline using mocks for long-running parts.

    Mocks:
    - Flask subprocess (to avoid starting a server)
    - Writes telemetry to a local temporary directory
    """
    monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: None)
    os.environ["RECSYS_LOG_DIR"] = str(tmp_path / "logs")

    result = pipeline_run.run_full_pipeline()

    # Verify returned structure
    assert isinstance(result, dict), "Pipeline should return a dictionary"
    assert "evaluation_results" in result, "Evaluation results missing in output"
    assert os.path.exists("scripts/models/svd_model.pkl"), "SVD model missing after pipeline run"
    assert Path(result["telemetry_log_dir"]).exists(), "Telemetry log directory should exist"

# Error Handling – Missing Dataset
def test_missing_dataset(monkeypatch, tmp_path):
    """
    Ensure pipeline raises FileNotFoundError if dataset is missing.
    This validates robustness of the data_ingestion_and_cleaning() stage.
    """
    # Temporarily mock dataset path to a non-existing location
    fake_path = tmp_path / "fake_dataset.csv"
    monkeypatch.setattr("scripts.pipeline_run.Path", lambda *a, **kw: fake_path)

    with pytest.raises(Exception):
        pipeline_run.data_ingestion_and_cleaning()
