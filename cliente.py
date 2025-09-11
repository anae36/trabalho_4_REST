import pika, json, threading
import base64, os
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


id_usuario = input("Digite seu id: ")
diretorio_public_keys = "C:/Users/Aninha/Documents/sd/public_key"
diretorio_private_keys = "C:/Users/Aninha/Documents/sd/private_key"
private_key_path = os.path.join(diretorio_private_keys, f"{id_usuario}_private.pem")
public_key_path = os.path.join(diretorio_public_keys, f"{id_usuario}.pem")


if not os.path.exists(private_key_path):
    print("Gerando novas chaves RSA...")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    pem_private_key = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    with open(private_key_path, "wb") as f:
        f.write(pem_private_key)

    pem_public_key = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with open(public_key_path, "wb") as f:
        f.write(pem_public_key)


with open(private_key_path, "rb") as key_file:
    private_key = serialization.load_pem_private_key(
        key_file.read(),
        password=None,
    )

def consumir_inicio_leilao():    
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
    channel = connection.channel()

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
   
    lance_json = json.dumps(lance,sort_keys=True)
    lance_bytes = lance_json.encode('utf-8')
    assinatura = private_key.sign(lance_bytes, padding.PKCS1v15(), hashes.SHA256())
    assinatura_b64 = base64.b64encode(assinatura).decode('utf-8')
    mensagem_para_enviar = {
        'dados': lance,
        'assinatura': assinatura_b64
    }
    mensagem_final_json = json.dumps(mensagem_para_enviar)
    
    
    channel_pub.basic_publish(exchange='lance_realizado_exchange',
                              routing_key='lance',
                              body=mensagem_final_json)
    print(f"Lance de R${valor} enviado para o leilão {id_leilao}!")


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
