from kafka import KafkaProducer
import json
import os
from dotenv import load_dotenv

load_dotenv()

producer = None

KAFKA_SERVER = os.getenv("KAFKA_SERVER")

def get_producer():
    global producer

    if producer is None:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_SERVER,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
    
    return producer

def enviar_tarefa(topico: str, evento: dict):
    prod = get_producer()
    prod.send(topico,evento)
    prod.flush()