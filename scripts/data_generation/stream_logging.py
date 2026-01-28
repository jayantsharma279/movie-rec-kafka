import os
import logging
from kafka import KafkaConsumer

# -----------------------
# Configure logging
# -----------------------
LOG_FILE = "kafka_status_logs.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s,%(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)

# -----------------------
# Setup Kafka consumer
# -----------------------
consumer = KafkaConsumer(
    'movielog17',
    bootstrap_servers=['localhost:9092'],
    auto_offset_reset='latest',  # earliest/latest/none
    enable_auto_commit=True,
    auto_commit_interval_ms=1000
)

print('Reading Kafka Broker...')

for message in consumer:
    msg_value = message.value.decode()
    
    # Print all messages (optional)
    # print(msg_value)
    
    # Check if 'status code' is in the message
    if 'recommendation request' in msg_value.lower():  # case-insensitive
        if 'status 200' not in msg_value.lower():  # case-insensitive
            # Print it
            print("⚠️ Request Failed:", msg_value)
            
            # Log it
            logging.info(msg_value)
