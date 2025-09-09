import pika, json

connection = pika.BlockingConnection(
    pika.ConnectionParameters(host='localhost'))
channel = connection.channel()


channel.exchange_declare(exchange='lance_validado_exchange', exchange_type= 'direct')
queue=channel.queue_declare(queue='lance_validado',durable=True)
channel.queue_bind(exchange='lance_validado_exchange', queue='lance_validado', routing_key = 'lance_valido')

channel.exchange_declare(exchange='leilao_vencedor_exchange', exchange_type= 'direct')
queue=channel.queue_declare(queue='leilao_vencedor',durable=True)
channel.queue_bind(exchange='leilao_vencedor_exchange', queue='leilao_vencedor', routing_key = 'vencedor')

def callback_lance_validado(ch, method, properties, body): 
    lance_decodificado = json.loads(body.decode('utf-8'))
    id_leilao = lance_decodificado.get('id_leilao')
    
    nome_fila_leilao = f"leilao_{id_leilao}"
    channel.queue_declare(queue=nome_fila_leilao, durable=True)
    channel.basic_publish(
            exchange='',
            routing_key=nome_fila_leilao,
            body=body 
        )
    
    print(f"[INFO]Lance publicado na fila leilao{id_leilao}")
    ch.basic_ack(delivery_tag=method.delivery_tag)

def callback_leilao_vencedor(ch, method, properties, body): 
    vencedor_decodificado = json.loads(body.decode('utf-8'))
    id_leilao = vencedor_decodificado.get('id_leilao')
    
    nome_fila_leilao = f"leilao_{id_leilao}"
    channel.queue_declare(queue=nome_fila_leilao, durable=True)
    channel.basic_publish(
            exchange='',
            routing_key=nome_fila_leilao,
            body=body
        )
    
    print(f"[INFO]Vencedor publicado na fila leilao{id_leilao}")
    ch.basic_ack(delivery_tag=method.delivery_tag)

channel.basic_consume(queue='lance_validado', on_message_callback=callback_lance_validado, auto_ack=False)
channel.basic_consume(queue='leilao_vencedor', on_message_callback=callback_leilao_vencedor, auto_ack=False)
print('[*] MS Notificação aguardando por eventos. Para sair pressione CTRL+C')
try:
    channel.start_consuming()
except KeyboardInterrupt:
    print('Interrompido')
    connection.close()