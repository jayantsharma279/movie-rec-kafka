import pandas as pd
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
import sys
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


DATA_DIR = ROOT_DIR / "dataset"
def main():
    log_path = DATA_DIR/"ratings.log"

    csv_path = DATA_DIR/"movie_ratings_log.csv"

    df = pd.read_csv(log_path, header=None, names=["timestamp", "userid", "movie_id", "rating"])


    df = df[["userid", "movie_id", "rating"]]
    df = df.head(10000)
    # Save to CSV without the index
    df.to_csv(csv_path, index=False)
    return csv_path    
