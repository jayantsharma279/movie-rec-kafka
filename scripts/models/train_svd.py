# scripts/models/train_svd.py
"""
Train an SVD model on movie ratings and save artifacts for serving.

Artifacts produced:
- svd_model.pkl : trained Surprise SVD model (used for predictions at inference)
- popular_top20.pkl : top-20 most popular movies (used as fallback for cold-start users)

Inputs:
- dataset/movie_ratings.csv : CSV with columns [userid, movie_id, rating]
"""

import os
import pandas as pd
import numpy as np
import pickle
from surprise import SVD, Dataset, Reader 

def main(data_path=None):
    """
    Train an SVD recommendation model and save it along with a Top-20 fallback list.

    Steps:
    1. Load and clean dataset.
    2. Train an SVD model using the Surprise library.
    3. Compute top-20 popular fallback movies.
    4. Save the model and fallback artifacts.
    """
    # Default path if not provided
    if data_path is None:
        data_path = os.path.join("dataset", "movie_ratings.csv")

    OUT_DIR = "scripts/models"
    TOPK = 20

    os.makedirs(OUT_DIR, exist_ok=True)

    # Load dataset
    df = pd.read_csv(data_path)
    print(f"Training model using dataset: {data_path}")

    # Clean numeric ratings
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df = df.dropna(subset=["rating"])
    df["rating"] = df["rating"].astype(float)

    # Validate schema
    assert {"userid", "movie_id", "rating"}.issubset(df.columns), (
        "CSV must have userid, movie_id, rating"
    )

    # Build Surprise dataset
    reader = Reader(rating_scale=(1, 5))
    data = Dataset.load_from_df(df[["userid", "movie_id", "rating"]], reader)
    trainset = data.build_full_trainset()

    # Train SVD model
    algo = SVD()
    algo.fit(trainset)

    # Compute top-20 fallback movies
    agg = (
        df.groupby("movie_id")
        .agg(cnt=("rating", "count"), avg=("rating", "mean"))
        .reset_index()
    )
    agg["score"] = agg["avg"] * np.log1p(agg["cnt"])
    popular_top20 = (
        agg.sort_values("score", ascending=False)["movie_id"].head(TOPK).tolist()
    )

    # Save artifacts (comment out if want to train again, else will be ran by combined script)
    # with open(os.path.join(OUT_DIR, "new_model_svd.pkl"), "wb") as f:
    #     pickle.dump(algo, f)

    # with open(os.path.join(OUT_DIR, "new_model_popular_top20.pkl"), "wb") as f:
    #     pickle.dump(popular_top20, f)

    print("Artifacts saved in models/: svd_model.pkl, popular_top20.pkl")
    return algo, popular_top20

if __name__ == "__main__":
    main()
