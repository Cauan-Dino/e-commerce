from celery import Celery
import os
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST","REDIS")
REDIS_PORT = os.getenv("REDIS_PORT","6379")
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

celery_app = Celery(
    'tarefas-e-commerce',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        'celery_app.tasks.envia_email',
        'celery_app.tasks.enviar_email_para_excluir_conta',
        'celery_app.tasks.nota_fiscal'
    ]
)

celery_app.conf.update(
    task_track_started=True,
    result_expires=3600,
    result_persistent=True,
    task_serializer='json',
    result_serializer='json',
    accept_content=['json']
)