"""
tests/test_app_flask.py

Unit tests for the Flask serving layer (app_flask.py).

These tests validate that:
- The Flask app starts and exposes the /recommend/<user_id> endpoint.
- Both cold-start and warm-start recommendation flows return valid responses.
- The API handles errors gracefully (e.g., missing model files).
"""

import pytest
import io
import os
import tempfile
import importlib

# Redirect TELEMETRY_DIR to a temporary directory for testing
tmp_dir = tempfile.mkdtemp()
os.environ["TELEMETRY_DIR"] = tmp_dir

from flask import Response
from app import app_flask


# Flask App Setup
def test_app_creation():
    """
    Ensure the Flask app initializes correctly.
    """
    assert hasattr(app_flask, "app"), "Flask app instance missing"
    client = app_flask.app.test_client()
    assert client is not None, "Flask test client could not be created"


# Cold-Start Recommendation
def test_cold_start_recommendations(monkeypatch):
    """
    Simulate a cold-start user (unknown ID). 
    Expect a 200 OK response and a comma-separated list of movie IDs.
    """

    # Mock `is_known_user` to always return False
    monkeypatch.setattr(app_flask, "is_known_user", lambda *a, **kw: False)

    client = app_flask.app.test_client()
    response = client.get("/recommend/test_new_user")

    assert response.status_code == 200, "API should return 200 for cold-start"
    data = response.data.decode("utf-8").strip()
    assert "," in data or data == "", "Cold-start response should be a list of IDs"
    assert isinstance(response, Response), "Response should be a Flask Response object"


# Warm-Start Recommendation
def test_warm_start_recommendations(monkeypatch):
    """
    Simulate a known user to verify warm-start recommendations work.
    """

    # Mock `is_known_user` to always return True
    monkeypatch.setattr(app_flask, "is_known_user", lambda *a, **kw: True)

    # Mock `top_k_for_user` to return predictable output
    monkeypatch.setattr(app_flask, "top_k_for_user", lambda uid, k=10: [(f"movie_{i}", 4.5) for i in range(k)])

    client = app_flask.app.test_client()
    response = client.get("/recommend/test_known_user")

    assert response.status_code == 200, "API should return 200 for warm-start"
    body = response.data.decode("utf-8").strip()
    movies = body.split(",")
    assert len(movies) == 10, "Expected 10 recommended movies in warm-start response"
    assert all(m.startswith("movie_") for m in movies), "All recommendations should follow mock pattern"


# Graceful Handling of Missing Models
def test_missing_model_files(monkeypatch):
    """
    Simulate missing model or fallback files and ensure the app can still import.
    """

    # Mock joblib.load to raise FileNotFoundError
    monkeypatch.setattr(app_flask, "joblib", type("FakeJoblib", (), {"load": staticmethod(lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))}))

    try:
        # Reimport the module to trigger the mocked behavior
        importlib.reload(app_flask)
    except Exception as e:
        pytest.fail(f"App should not crash when model files are missing: {e}")
