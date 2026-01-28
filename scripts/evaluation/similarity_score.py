import pandas as pd
import os

def compute_overlap(train_path: str, val_path: str, test_path: str = None):
    print(" Checking for potential data leakage...\n")
    train = pd.read_csv(train_path)
    val = pd.read_csv(val_path)
    test = pd.read_csv(test_path) if test_path else None


    for df, name in zip([train, val, test], ['train', 'val', 'test']):
        if df is not None:
            assert {'userid', 'movie_name'}.issubset(df.columns), f"{name} missing userId/movieId columns."

    def overlap_score(a, b, name_a, name_b):
        """Compute overlap between two sets of user-movie pairs."""
        set_a = set(zip(a['userid'], a['movie_name']))
        set_b = set(zip(b['userid'], b['movie_name']))

        intersection = set_a.intersection(set_b)
        overlap_pct = 100 * len(intersection) / min(len(set_a), len(set_b))
        print(f" Overlap between {name_a} and {name_b}: {len(intersection)} pairs ({overlap_pct:.2f}%)")

        # Optional: also check shared users and movies
        user_overlap = len(set(a['userid']).intersection(set(b['userid'])))
        movie_overlap = len(set(a['movie_name']).intersection(set(b['movie_name'])))
        print(f"   - Shared users: {user_overlap} ({100*user_overlap/min(len(a['userid'].unique()), len(b['userid'].unique())):.2f}%)")
        print(f"   - Shared movies: {movie_overlap} ({100*movie_overlap/min(len(a['movie_name'].unique()), len(b['movie_name'].unique())):.2f}%)\n")

    overlap_score(train, val, 'train', 'val')
    if test is not None:
        overlap_score(train, test, 'train', 'test')
        overlap_score(val, test, 'val', 'test')

    print(" Leakage check complete.\n")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "../.."))

TRAIN_PATH = os.path.join(PROJECT_ROOT, "dataset", "movie_ratings.csv")
VAL_PATH = os.path.join(PROJECT_ROOT, "dataset", "movie_ratings_val.csv")

compute_overlap(train_path=TRAIN_PATH,val_path=VAL_PATH)
