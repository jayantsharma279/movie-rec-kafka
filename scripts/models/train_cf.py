# scripts/models/train_cf.py
"""
Train a User-User Collaborative Filtering (KNNBasic) model on movie ratings
and save artifacts for serving.

Artifacts produced:
- user_cf_model.pkl : trained Surprise KNNBasic model (used for predictions at inference)

Inputs:
- dataset/movie_ratings.csv : CSV with columns [userid, movie_id, rating]
"""

import os
import pandas as pd
import pickle
from surprise import Dataset, Reader, KNNBasic


def main():
    """
    Train a User-User Collaborative Filtering model and save it as a pickle file.

    Steps:
    1. Load the dataset.
    2. Clean and validate the data.
    3. Build the Surprise training set.
    4. Train the KNNBasic model.
    5. Persist the model artifact.
    """
    # Configuration
    DATA_PATH = "dataset/movie_ratings.csv"
    OUT_DIR = "scripts/models"

    # Ensure output directory exists
    os.makedirs(OUT_DIR, exist_ok=True)

    # Load ratings dataset
    df = pd.read_csv(DATA_PATH)

    # Ensure ratings are numeric and drop invalid rows
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df = df.dropna(subset=["rating"])
    df["rating"] = df["rating"].astype(float)

    # Validate required columns
    assert {"userid", "movie_id", "rating"}.issubset(df.columns), (
        "CSV must have userid, movie_id, rating"
    )

    # Build Surprise dataset
    reader = Reader(rating_scale=(1, 5))
    data = Dataset.load_from_df(df[["userid", "movie_id", "rating"]], reader)
    trainset = data.build_full_trainset()

    # Train the User-User CF model
    algo = KNNBasic(sim_options={"name": "cosine", "user_based": True})
    algo.fit(trainset)

    # Save the model artifact
    model_path = os.path.join(OUT_DIR, "user_cf_model.pkl")
    with open(model_path, "wb") as f:
        pickle.dump(algo, f)

    print(f"Artifacts saved in models/: {model_path}")
    return algo


if __name__ == "__main__":
    main()
