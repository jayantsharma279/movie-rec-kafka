#!/usr/bin/env python3
import os, re, sys
from kafka import KafkaConsumer  # keep this import; not used in stdin mode

WATCH_LOG = "/var/log/recsys/watches.log"
RATING_LOG  = "/var/log/recsys/ratings.log"
BROKERS = os.environ.get("KAFKA_BROKERS", "localhost:9092")
TOPIC   = os.environ.get("KAFKA_TOPIC_LOGS", "server-logs")

# Watch-start pattern
RX_WATCH = re.compile(r"""
    ^(?P<ts>[^,]+),
    (?P<uid>[^,]+),
    GET\s+/data/m/(?P<mid>[^/]+)/(?P<minute>\d+)\.mpg
""", re.X)

# Rating pattern: <time>,<userid>,GET /rate/<movieid>=<rating>
RX_RATE = re.compile(r"""
    ^(?P<ts>[^,]+),
    (?P<uid>[^,]+),
    GET\s+/rate/(?P<mid>[^=]+)=(?P<rating>[1-5])
""", re.X)

def handle_line(line, watch_f, rating_f):
    if not line: 
        return
    line = line.strip()
    if not line: #if issues parsing kafka line, return
        return 
    m = RX_WATCH.match(line)
    if m:
        # Extra safety: ensure we really have 3 CSV parts
        parts = line.split(",", 3)
        if len(parts) < 3:
            return

        minute_str = m.group("minute")
        try:
            minute = int(minute_str)
        except ValueError:
            return

        if minute not in (0, 1):
            return

        ts  = m.group("ts")
        uid = m.group("uid")
        mid = m.group("mid")

        # ts,user_id,movie_id,minute
        watch_f.write(f"{ts},{uid},{mid},{minute}\n")
        watch_f.flush()

    r = RX_RATE.match(line)
    if r:
        ts  = r.group("ts")
        uid = r.group("uid")
        mid = r.group("mid")
        rating_str = r.group("rating")

        try:
            rating = float(rating_str)
        except ValueError:
            return

        # ts,user_id,movie_id,rating
        rating_f.write(f"{ts},{uid},{mid},{rating}\n")
        rating_f.flush()

def main():
    os.makedirs(os.path.dirname(WATCH_LOG), exist_ok=True)

    mode_stdin = (BROKERS.strip().lower() == "stdin")

    # Open both logs once and reuse the handles
    with open(WATCH_LOG, "a", encoding="utf-8") as watch_out, \
         open(RATING_LOG, "a", encoding="utf-8") as rating_out:

        if mode_stdin:
            # read lines from STDIN
            for line in sys.stdin:
                handle_line(line, watch_out, rating_out)
            return 0

        # normal Kafka mode
        consumer = KafkaConsumer(
            TOPIC,
            bootstrap_servers=[b.strip() for b in BROKERS.split(",") if b.strip()],
            auto_offset_reset="latest",
            enable_auto_commit=True,
            group_id="recsys-watch-consumer",
            value_deserializer=lambda x: x.decode("utf-8", errors="ignore"),
        )
        for msg in consumer:
            handle_line(msg.value, watch_out, rating_out)

    
    

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
