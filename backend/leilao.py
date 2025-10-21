import pika, time, datetime, json

connection = pika.BlockingConnection(
    pika.ConnectionParameters(host='localhost'))
channel = connection.channel()

# Hora atual
agora = datetime.datetime.now()

leiloes=[
    {
        "id": 1,
        "descricao": "Pc da Marcela",
        "hora_inicio": agora+datetime.timedelta(seconds=5),
        "hora_fim": agora+datetime.timedelta(seconds=100),
        "status":"Pendente"
    },
    {
        "id": 2,
        "descricao": "Pc da aninha",
        "hora_inicio": agora+datetime.timedelta(seconds=15),
        "hora_fim": agora+datetime.timedelta(seconds=150),
        "status":"Pendente"
    },
    {
        "id": 3,
        "descricao": "Pc do matheus",
        "hora_inicio": agora+datetime.timedelta(seconds=17),
        "hora_fim": agora+datetime.timedelta(seconds=200),
        "status":"Pendente"
    }
]

#fila leilão iniciado - única fanout 
channel.queue_declare(queue='leilao_iniciado')
channel.exchange_declare(exchange='leilao_inicio_exchange',
                         exchange_type='fanout')
channel.queue_bind(exchange='leilao_inicio_exchange', queue='leilao_iniciado')

#fila leilão finalizado
channel.queue_declare(queue='leilao_finalizado')
channel.exchange_declare(exchange='leilao_fim_exchange',
                         exchange_type='direct')
channel.queue_bind(exchange='leilao_fim_exchange', queue='leilao_finalizado',routing_key='black')

try:
    while True:
        hora_atual = datetime.datetime.now()
        for leilao in leiloes:
            if leilao['status']=='Pendente' and leilao['hora_inicio']<=hora_atual:
                leilao['status']='Ativo'
                mensagem = {
                        "id_leilao": leilao['id'],
                        "descricao": leilao['descricao'],
                        "hora_inicio": leilao['hora_inicio'].isoformat() #objetos datetime não são serializáveis em json diretamente
                    }
                
                mensagem_json=json.dumps(mensagem)
                channel.basic_publish(exchange='leilao_inicio_exchange',
                                        routing_key='',
                                        body=mensagem_json)
                
            elif leilao['status'] == 'Ativo' and leilao['hora_fim'] <= hora_atual:
                    leilao['status'] = 'Encerrado'
                    
                    mensagem = {
                        "id_leilao": leilao['id'],
                        "descricao": leilao['descricao'],
                        "hora_fim": leilao['hora_fim'].isoformat()
                    }    
                    mensagem_json=json.dumps(mensagem)
                    
                    channel.basic_publish(exchange='leilao_fim_exchange',
                                        routing_key='black',
                                        body=mensagem_json)            
        time.sleep(1)  
                
except KeyboardInterrupt:
    print("\nPrograma interrompido pelo usuário.")
finally:  
    if 'connection' in locals() and connection.is_open:
        connection.close()
        print("Conexão com RabbitMQ fechada.")      



