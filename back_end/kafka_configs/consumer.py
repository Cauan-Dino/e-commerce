from kafka import KafkaConsumer
import os
from dotenv import load_dotenv
import json

load_dotenv()

KAFKA_SERVER = os.getenv('KAFKA_SERVER')

consumers = KafkaConsumer(
    'enviar_email',
    bootstrap_servers=KAFKA_SERVER,  
    group_id='grupo_processadores',
    value_deserializer=lambda v: json.loads(v.decode('utf-8'))
)