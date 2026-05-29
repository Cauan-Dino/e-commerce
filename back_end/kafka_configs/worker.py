from kafka_configs.consumer import consumers
from kafka_configs.tasks.envia_email import enviar_email 
from kafka_configs.tasks.enviar_email_para_excluir_conta import enviar_email_para_excluir_conta

# Dicionario com as tarefas
TAREFAS = {
    'enviar_email': enviar_email,
    'enviar_email_para_excluir_conta':enviar_email_para_excluir_conta
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