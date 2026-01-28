# scripts/models/eval_models.py
"""
Evaluate and compare two recommendation models:
1. SVD (Matrix Factorization)
2. User-User Collaborative Filtering (KNNBasic)

Dimensions measured:
1. Prediction accuracy (RMSE, MAE)
2. Training cost (time in seconds)
3. Inference cost (avg latency per request in ms)
4. Model size on disk (MB)
"""

import time
import pickle
import os
import pandas as pd
from surprise import SVD, KNNBasic, Dataset, Reader
from surprise.model_selection import cross_validate


def main():
    """
    Evaluate both SVD and User-User CF models and store the comparison results.

    Steps:
    1. Load and clean dataset.
    2. Evaluate each model for accuracy, training time, latency, and model size.
    3. Save comparison results as a CSV file.
    """
    DATA_PATH = "dataset/movie_ratings.csv"
    RESULTS_DIR = "scripts/models/"

    # Load dataset
    df = pd.read_csv(DATA_PATH)
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df = df.dropna(subset=["rating"])
    df["rating"] = df["rating"].astype(float)

    reader = Reader(rating_scale=(1, 5))
    data = Dataset.load_from_df(df[["userid", "movie_id", "rating"]], reader)

    def evaluate_model(name, algo, model_path):
        """
        Evaluate an algorithm using multiple criteria:
        - RMSE, MAE via cross-validation
        - Training time
        - Inference latency
        - Model size
        """
        results = {}

        # Accuracy evaluation
        cv_results = cross_validate(algo, data, measures=["RMSE", "MAE"], cv=5, verbose=False)
        results["RMSE"] = cv_results["test_rmse"].mean()
        results["MAE"] = cv_results["test_mae"].mean()

        # Training time
        trainset = data.build_full_trainset()
        start = time.time()
        algo.fit(trainset)
        end = time.time()
        results["train_time_sec"] = end - start

        # Inference latency
        sample = df.sample(n=100, random_state=42)
        start = time.time()
        for _, row in sample.iterrows():
            algo.predict(row["userid"], row["movie_id"])
        end = time.time()
        results["latency_ms"] = (end - start) / len(sample) * 1000

        # Model size
        with open(model_path, "wb") as f:
            pickle.dump(algo, f)
        size_bytes = os.path.getsize(model_path)
        results["size_mb"] = size_bytes / (1024 * 1024)

        return results

    # Evaluate both models
    svd_results = evaluate_model("SVD", SVD(), os.path.join(RESULTS_DIR, "svd_model.pkl"))
    cf_results = evaluate_model(
        "User-User CF",
        KNNBasic(sim_options={"name": "cosine", "user_based": True}),
        os.path.join(RESULTS_DIR, "user_cf_model.pkl"),
    )

    # Store and print comparison results
    df_results = pd.DataFrame([svd_results, cf_results], index=["SVD", "User-User CF"])
    df_results.to_csv(os.path.join(RESULTS_DIR, "model_comparison.csv"), index=True)

    print("Model comparison results saved to model_comparison.csv")
    print(df_results)

    return df_results


if __name__ == "__main__":
    main()
