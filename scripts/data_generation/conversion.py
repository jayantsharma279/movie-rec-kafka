import pandas as pd

def main():
    # Load CSV
    df = pd.read_csv("movie_watch.csv")

    # Create movie_id column
    df["movie_id"] = df["movie_name"].str.replace(" ", "+", regex=False) + '+' + df["year"].astype(str)

    # Save back to CSV
    df.to_csv("movie_watch.csv", index=False)
    print(df.head())
if __name__ == "__main__":
    main()
