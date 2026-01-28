import pickle
import pandas as pd
import numpy as np
from surprise import Dataset, Reader, accuracy
from collections import defaultdict
import os

# ========== CONFIG ==========
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "../.."))

VAL_PATH = os.path.join(PROJECT_ROOT, "dataset", "movie_ratings_val.csv")
MODEL_PATH = os.path.join(PROJECT_ROOT, "scripts", "models", "svd_model.pkl")

RATING_SCALE = (1, 5)
TOPK = 5
# ============================


def evaluate_rmse_mae(model, val_df):
    """Compute RMSE and MAE on validation data."""
    reader = Reader(rating_scale=RATING_SCALE)
    data = Dataset.load_from_df(val_df[['userid', 'movie_id', 'rating']], reader)
    testset = data.construct_testset(data.raw_ratings)
    predictions = model.test(testset)

    rmse = accuracy.rmse(predictions, verbose=False)
    mae = accuracy.mae(predictions, verbose=False)
    print(f"RMSE: {rmse:.4f} | MAE: {mae:.4f}")
    return predictions


def evaluate_topk_metrics(predictions, k=TOPK):
    """Compute Hit Ratio@k and NDCG@k for top-N recommendations."""
    hits, ndcgs, users = 0, 0, defaultdict(list)

    # Group predictions by user
    for uid, iid, true_r, est, _ in predictions:
        users[uid].append((iid, true_r, est))

    for uid, items in users.items():
        # Sort items by predicted rating
        items_sorted = sorted(items, key=lambda x: x[2], reverse=True)
        top_k = [i[0] for i in items_sorted[:k]]
        liked = [i for i, r, _ in items if r >= 4]  # threshold for "liked" items

        for idx, iid in enumerate(top_k):
            if iid in liked:
                hits += 1
                ndcgs += 1 / np.log2(idx + 2)
                break

    n_users = len(users)
    hr = hits / n_users if n_users else 0.0
    ndcg = ndcgs / n_users if n_users else 0.0

    print(f" Hit Ratio@{k}: {hr:.4f} | NDCG@{k}: {ndcg:.4f}")


if __name__ == "__main__":
    print(" Loading trained SVD model...")
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)

    print(" Loading validation dataset...")
    val_df = pd.read_csv(VAL_PATH)
    val_df = val_df[pd.to_numeric(val_df['rating'], errors='coerce').notnull()]
    val_df['rating'] = val_df['rating'].astype(float)

    print(" Evaluating model on validation dataset:")
    preds = evaluate_rmse_mae(model, val_df)
    evaluate_topk_metrics(preds, k=TOPK)

#Last results: 
# RMSE: 0.6825 | MAE: 0.5287
#  Hit Ratio@5: 0.7934 | NDCG@5: 0.7934
