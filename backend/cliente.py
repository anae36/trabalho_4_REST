import pika, json, threading
import base64, os
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


id_usuario = input("Digite seu id: ")

def consumir_inicio_leilao():    
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
    channel = connection.channel()
    #exchange, fila temporária e bind 
    channel.exchange_declare(exchange='leilao_inicio_exchange', exchange_type='fanout')
    queue = channel.queue_declare(queue='', exclusive=True)
    queue_name = queue.method.queue
    channel.queue_bind(exchange='leilao_inicio_exchange', queue=queue_name)

    def callback(ch, method, properties, body):
        dados_leilao = json.loads(body.decode('utf-8'))
        print("\n--- NOVO LEILÃO INICIADO ---")
        print(f"Id do Leilão: {dados_leilao.get('id_leilao')}")
        print(f"Descrição: {dados_leilao.get('descricao')}")
        print(f"Início: {dados_leilao.get('hora_inicio')}")
        print("--------------------------\n")
                
    channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)
    print("[*] Escutando por novos leilões...")
    channel.start_consuming()

def consumir_leilao_especifico(id_leilao):   
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
    channel = connection.channel()
    
    #exchange topic 
    channel.exchange_declare(exchange='notificacoes_exchange', exchange_type='topic')
    result = channel.queue_declare(queue='', exclusive=True)
    queue_name_exclusiva = result.method.queue
    channel.queue_bind(
        exchange='notificacoes_exchange',
        queue=queue_name_exclusiva,
        routing_key=f"*.leilao.{id_leilao}"    )    
    
    def callback_leilao(ch, method, properties, body):
        dados_leilao = json.loads(body.decode('utf-8'))
        print(f"\n[Notificação Leilão {id_leilao}]: {dados_leilao}")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(
        queue=queue_name_exclusiva,
        on_message_callback=callback_leilao,
        auto_ack=False
    )

    print(f"[*] Inscrito para receber notificações do leilão {id_leilao}.")
    channel.start_consuming()
connection_pub = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
channel_pub = connection_pub.channel()
channel_pub.queue_declare(queue='lance_realizado', durable=True)
channel_pub.exchange_declare(exchange='lance_realizado_exchange', exchange_type='direct')
channel_pub.queue_bind(exchange='lance_realizado_exchange', queue='lance_realizado', routing_key='lance')

def realiza_lances(id_leilao, id_usuario_lance, valor):
    lance = {
        "id_leilao": (id_leilao),
        "id_usuario": id_usuario_lance,
        "valor": float(valor)
    }
   
    mensagem_para_enviar = {
        'dados': lance
    }
    mensagem_final_json = json.dumps(mensagem_para_enviar)
    
    
    channel_pub.basic_publish(exchange='lance_realizado_exchange',
                              routing_key='lance',
                              body=mensagem_final_json)
    print(f"Lance de R${valor} enviado para o leilão {id_leilao}!")

#thread para ouvir o início dos leilões
consumer_thread = threading.Thread(target=consumir_inicio_leilao)
consumer_thread.daemon = True
consumer_thread.start()

leiloes_inscritos = set()
threads_leiloes = {} 

try:
    while True:
        opcao = input("\nPara dar um lance digite 1, para sair digite 2: ")
        if opcao == "2":
            print("Usuário saiu.")
            break
        elif opcao == "1":
            leilao_id = input("Digite o id do leilão: ")
            valor = input("Digite o valor do lance: ")
            realiza_lances(leilao_id, id_usuario, valor)
            
            #cria uma nova thread pra escutar um leilao especifico
            if leilao_id not in leiloes_inscritos:
                thread_leilao = threading.Thread(target=consumir_leilao_especifico, args=(leilao_id,))
                thread_leilao.daemon = True
                thread_leilao.start()
                leiloes_inscritos.add(leilao_id)
                threads_leiloes[leilao_id] = thread_leilao
        else:
            print("Opção inválida.")
finally:
    print("Fechando conexão de publicação...")
    connection_pub.close()
