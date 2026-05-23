from kafka_configs.consumer import consumers
from kafka_configs.tasks.envia_email import enviar_email 

# Dicionario com as tarefas
TAREFAS = {
    'enviar_email': enviar_email
}

for consumer in consumers:
    dict_info = consumer.value
    topico = consumer.topic
    # Pega a tarefa de acordo com o topico
    task = TAREFAS.get(topico)
    # Pula caso a task não exista
    if not task:
        pass
    # Executa a task
    task(dict_info)