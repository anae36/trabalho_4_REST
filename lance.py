import pika
import json
import base64
import os
import traceback
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature

diretorio_public_keys = "C:/Users/Aninha/Documents/sd/public_key"
chaves_publicas = {}
leiloes_ativos = {}

def carregar_chaves_publicas():
    print("Carregando chaves públicas...")
    for filename in os.listdir(diretorio_public_keys):
        if filename.endswith(".pem"):
            id_cliente = filename.split('.')[0]
            filepath = os.path.join(diretorio_public_keys, filename)
            with open(filepath, "rb") as key_file:
                public_key = serialization.load_pem_public_key(key_file.read())
                chaves_publicas[id_cliente] = public_key
                print(f"  - Chave de '{id_cliente}' carregada.")
    print("Carregamento de chaves concluído.")

connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
channel = connection.channel()

carregar_chaves_publicas()


channel.exchange_declare(exchange='leilao_inicio_exchange', exchange_type='fanout')
q = channel.queue_declare(queue='', exclusive=True)    
queue_name = q.method.queue
channel.queue_bind(exchange='leilao_inicio_exchange', queue=queue_name)

channel.exchange_declare(exchange='leilao_fim_exchange', exchange_type='direct')
channel.queue_declare(queue='leilao_finalizado')
channel.queue_bind(exchange='leilao_fim_exchange', queue='leilao_finalizado', routing_key='black')

channel.exchange_declare(exchange='lance_realizado_exchange', exchange_type='direct')
channel.queue_declare(queue='lance_realizado', durable=True)
channel.queue_bind(exchange='lance_realizado_exchange', queue='lance_realizado', routing_key='lance')

channel.exchange_declare(exchange='lance_validado_exchange', exchange_type='direct')
channel.queue_declare(queue='lance_validado', durable=True)
channel.queue_bind(exchange='lance_validado_exchange', queue='lance_validado', routing_key='lance_valido')

channel.exchange_declare(exchange='leilao_vencedor_exchange', exchange_type='direct')
channel.queue_declare(queue='leilao_vencedor', durable=True)
channel.queue_bind(exchange='leilao_vencedor_exchange', queue='leilao_vencedor', routing_key='vencedor')


def callback_leilao_iniciado(ch, method, properties, body):
    try:
        dados = json.loads(body.decode('utf-8'))
    except Exception as e:
        print("[ERRO] Falha ao decodificar leilao_iniciado:", e)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

   
    raw_id = dados.get('id_leilao', dados.get('id'))
    if raw_id is None:
        print("[ERRO] Mensagem de leilao_iniciado sem id_leilao:", dados)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    
    id_leilao = str(raw_id)
    print(f"[INFO] Leilão {id_leilao} iniciado.")
    leiloes_ativos[id_leilao] = {
        "id_leilao": id_leilao,
        "maior_lance": 0,
        "lances": []
    }
    ch.basic_ack(delivery_tag=method.delivery_tag)


def callback_leilao_finalizado(ch, method, properties, body):
    try:
        dados = json.loads(body.decode('utf-8'))
    except Exception as e:
        print("[ERRO] Falha ao decodificar leilao_finalizado:", e)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    raw_id = dados.get('id_leilao', dados.get('id'))
    if raw_id is None:
        print("[ERRO] leilao_finalizado sem id:", dados)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    id_leilao = str(raw_id)
    leilao = leiloes_ativos.get(id_leilao) or leiloes_ativos.get(int(raw_id)) if isinstance(raw_id, (str, int)) else None

    if leilao:
        print(f"[INFO] Leilão {id_leilao} finalizado. Determinando o vencedor...")
        if leilao['lances']:
            lance_vencedor = max(leilao['lances'], key=lambda x: x['valor'])
            vencedor_id = lance_vencedor['id_usuario']
            valor_final = lance_vencedor['valor']
            mensagem_vencedor = {
                "id_leilao": id_leilao,
                "id_vencedor": vencedor_id,
                "valor": valor_final
            }
            channel.basic_publish(exchange='leilao_vencedor_exchange', routing_key='vencedor', body=json.dumps(mensagem_vencedor))
            print(f"[SUCESSO] Vencedor do leilão {id_leilao} é {vencedor_id} com R${valor_final}.")
        else:
            print(f"[INFO] Leilão {id_leilao} terminou sem lances.")
        
        if id_leilao in leiloes_ativos:
            del leiloes_ativos[id_leilao]
    else:
        print(f"[AVISO] Finalização recebida para leilão desconhecido ({id_leilao}). Ignorado.")

    ch.basic_ack(delivery_tag=method.delivery_tag)


def callback_lance(ch, method, properties, body):
    try:
        mensagem_completa = json.loads(body.decode('utf-8'))
        dados_lance = mensagem_completa.get('dados')
        if dados_lance is None:
            print("[ERRO] Mensagem sem campo 'dados':", mensagem_completa)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return        
        if isinstance(dados_lance, str):
            try:
                dados_lance = json.loads(dados_lance)
                
            except Exception as e:               
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return        
        raw_id = dados_lance.get('id_leilao', dados_lance.get('id'))
        if raw_id is None:
            print("[ERRO] dados_lance sem id_leilao:", dados_lance)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        id_leilao_str = str(raw_id)
        id_usuario = str(dados_lance.get('id_usuario')) if dados_lance.get('id_usuario') is not None else None

        leilao = leiloes_ativos.get(id_leilao_str)
        if leilao is None:
            try:
                leilao = leiloes_ativos.get(int(raw_id))
                if leilao:
                    print("[DEBUG] Leilão encontrado usando chave int.")
            except Exception:
                pass

        if not leilao:
            print(f"[AVISO] Lance recebido para leilão desconhecido ({id_leilao_str}). Descartado.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        if id_usuario is None or id_usuario not in chaves_publicas:
            print(f"[FALHA] Lance de usuário desconhecido '{id_usuario}'. Descartado.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        dados_json = json.dumps(dados_lance, sort_keys=True)
        dados_bytes = dados_json.encode('utf-8')

        assinatura_b64 = mensagem_completa.get('assinatura')
        if not assinatura_b64:
            print("[ERRO] Mensagem sem assinatura:", mensagem_completa)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        assinatura_bytes = base64.b64decode(assinatura_b64)
        chave_publica = chaves_publicas[id_usuario]    
        chave_publica.verify(assinatura_bytes, dados_bytes, padding.PKCS1v15(), hashes.SHA256())

        valor_lance = float(dados_lance.get('valor', 0))

        if valor_lance > leilao['maior_lance']:
            print(f"[SUCESSO] Lance de R${valor_lance} de {id_usuario} para o leilão {id_leilao_str} é VÁLIDO e MAIOR.")
            leilao['maior_lance'] = valor_lance
            leilao['lances'].append(dados_lance)
            channel.basic_publish(exchange='lance_validado_exchange', routing_key='lance_valido', body=json.dumps(dados_lance))
        else:
            print(f"[FALHA] Lance de R${valor_lance} de {id_usuario} é MENOR ou IGUAL ao lance atual (R${leilao['maior_lance']}).")

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except InvalidSignature:
        print(f"[FALHA] ASSINATURA INVÁLIDA para o usuário {id_usuario}! Lance descartado.")
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"[ERRO] Erro inesperado no processamento do lance: {e}")
        traceback.print_exc()
        ch.basic_ack(delivery_tag=method.delivery_tag)


channel.basic_consume(queue='lance_realizado', on_message_callback=callback_lance, auto_ack=False)
channel.basic_consume(queue=queue_name, on_message_callback=callback_leilao_iniciado, auto_ack=False)
channel.basic_consume(queue='leilao_finalizado', on_message_callback=callback_leilao_finalizado, auto_ack=False)

print('[*] Microsserviço de Lances aguardando mensagens. Para sair pressione CTRL+C')
channel.start_consuming()
