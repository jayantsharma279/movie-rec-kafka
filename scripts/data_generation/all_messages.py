import os
from datetime import datetime
from json import dumps, loads
from time import sleep
from random import randint
from kafka import KafkaConsumer
from typing import Dict, Any
import re


consumer = KafkaConsumer('movielog17',
    bootstrap_servers=['localhost:9092'],
    auto_offset_reset='latest', #Experiment with different values (earliest, latest, none)
    # Commit that an offset has been read
    enable_auto_commit=True,
    # How often to tell Kafka, an offset has been read
    auto_commit_interval_ms=1000
)

print('Reading Kafka Broker')
for message in consumer:
    message = message.value.decode()
    # Default message.value type is bytes!
    print((message))