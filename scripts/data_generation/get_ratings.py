import os
import re
from kafka import KafkaConsumer
from pathlib import Path

def main(output_filename: str):

    dataset_dir = Path(__file__).resolve().parents[2] / "dataset"
    # dataset_dir.mkdir(exist_ok=True)
    print(dataset_dir)

    output_path = dataset_dir / output_filename

    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "host.docker.internal:9092")

    consumer = KafkaConsumer(
        'movielog17',
        bootstrap_servers=bootstrap,
        auto_offset_reset='latest',
        enable_auto_commit=True,
        auto_commit_interval_ms=1000
    )

    print(f"Reading Kafka Broker... Writing to {output_filename}")

    count = 0 

    with open(output_path, "w", encoding="utf-8") as f_ratings:
        f_ratings.write("userid,movie_name,year,rating,movie_id\n")

        for msg in consumer:
            line = msg.value.decode("utf-8", errors="replace").strip()
            parts = line.split(",", 2)

            if len(parts) < 3:
                continue

            userid = parts[1].strip()
            rest = parts[2].strip()

            # ---------------------------
            # Case 1: Ratings (/rate/)
            # ---------------------------
            if rest.startswith("GET /rate/"):
                raw = rest.replace("GET /rate/", "")

                if "=" in raw:
                    movie_with_year, rating = raw.split("=", 1)

                    match = re.match(r"(.+)(\d{4})$", movie_with_year)
                    if match:
                        movie_raw = match.group(1).rstrip("+")
                        year = match.group(2)
                        movie_name = movie_raw.replace("+", " ").strip()

                        movie_raw_clean = movie_raw.strip("+").replace(" ", "+")
                        movie_id = f"{movie_raw_clean}+{year}".replace("++", "+").lower()

                        final_line = f"{userid},{movie_name},{year},{rating.strip()},{movie_id}"
                        f_ratings.write(final_line + "\n")

                        count += 1

                        if count == 10:  # Only make 10 vals for testing
                            break
                        if count % 1000 == 0:
                            print("Data saved till now:", count)

            else:
                continue


if __name__ == "__main__":
    # Example: python kafka_consumer.py output.csv
    import sys
    if len(sys.argv) < 2:
        print("Usage: python kafka_consumer.py <output_filename>")
        sys.exit(1)

    output_filename = sys.argv[1]
    main(output_filename)
