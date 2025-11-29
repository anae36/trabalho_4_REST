import pika, json, threading, time
from flask import Flask, request, jsonify

app = Flask(__name__)

leiloes_ativos = {} # {"id_leilao": {"maior_lance": 0, "lances": []}}

@app.route('/lances', methods=['POST'])
def receber_lance():
    dados = request.json
    id_leilao = str(dados.get('id_leilao'))
    id_usuario = str(dados.get('id_usuario'))
    valor_lance = float(dados.get('valor', 0))

    connection_pub = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
    channel_pub = connection_pub.channel()

    try:
        leilao = leiloes_ativos.get(id_leilao)
        
        if not leilao:
            print(f"[MS Lance] Lance REPROVADO (Leilão {id_leilao} não está ativo).")
            publicar_lance_invalidado(channel_pub, dados, "leilao_inativo")
            return jsonify({"status": "erro", "motivo": "leilao_inativo"}), 400

        if valor_lance <= leilao['maior_lance']:
            print(f"[MS Lance] Lance REPROVADO (Valor R${valor_lance} é menor ou igual a R${leilao['maior_lance']}).")
            publicar_lance_invalidado(channel_pub, dados, "valor_baixo")
            return jsonify({"status": "erro", "motivo": "valor_baixo"}), 400
            
        print(f"[MS Lance] Lance APROVADO (R${valor_lance} de {id_usuario} no leilão {id_leilao}).")
        leilao['maior_lance'] = valor_lance
        leilao['lances'].append(dados)
        
        channel_pub.exchange_declare(exchange='lance_validado_exchange', exchange_type='direct')
        channel_pub.basic_publish(
            exchange='lance_validado_exchange',
            routing_key='lance_valido',
            body=json.dumps(dados)
        )
        
        return jsonify({"status": "sucesso", "lance": dados}), 201

    finally:
        connection_pub.close()

def publicar_lance_invalidado(channel, dados_lance, motivo):
    channel.exchange_declare(exchange='lance_invalidado_exchange', exchange_type='direct')
    mensagem = {
        "lance": dados_lance,
        "motivo": motivo,
        "id_usuario": dados_lance.get('id_usuario')
    }
    channel.basic_publish(
        exchange='lance_invalidado_exchange',
        routing_key='lance_invalido',
        body=json.dumps(mensagem)
    )

def iniciar_consumidor_rabbitmq():
    print("[MS Lance] Conectando ao RabbitMQ...")
    connection = None
    channel = None
    
    while True:
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
            channel = connection.channel()
            print("[MS Lance] Conectado ao RabbitMQ com sucesso!")
            break
        except pika.exceptions.AMQPConnectionError:
            print("[MS Lance] RabbitMQ indisponível. Tentando em 5s...")
            time.sleep(5)

    channel.exchange_declare(exchange='leilao_inicio_exchange', exchange_type='fanout')
    q_inicio = channel.queue_declare(queue='', exclusive=True)
    channel.queue_bind(exchange='leilao_inicio_exchange', queue=q_inicio.method.queue)

    channel.exchange_declare(exchange='leilao_fim_exchange', exchange_type='direct')
    q_fim = channel.queue_declare(queue='leilao_finalizado')
    channel.queue_bind(exchange='leilao_fim_exchange', queue=q_fim.method.queue, routing_key='black')

    channel.exchange_declare(exchange='leilao_vencedor_exchange', exchange_type='direct')

    def callback_leilao_iniciado(ch, method, properties, body):
        dados = json.loads(body.decode('utf-8'))
        id_leilao = str(dados.get('id_leilao'))
        if id_leilao not in leiloes_ativos:
            leiloes_ativos[id_leilao] = {
                "id_leilao": id_leilao,
                "maior_lance": float(dados.get('valor_inicial', 0)),
                "lances": []
            }
            print(f"[MS Lance] Leilão {id_leilao} agora está ATIVO.")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def callback_leilao_finalizado(ch, method, properties, body):
        dados = json.loads(body.decode('utf-8'))
        id_leilao = str(dados.get('id_leilao'))
        
        leilao = leiloes_ativos.get(id_leilao)
        
        if leilao:
            print(f"[MS Lance] Leilão {id_leilao} FINALIZADO. Determinando vencedor...")
            if leilao['lances']:
                lance_vencedor = max(leilao['lances'], key=lambda x: x['valor'])
                mensagem_vencedor = {
                    "id_leilao": id_leilao,
                    "id_vencedor": lance_vencedor['id_usuario'],
                    "valor": lance_vencedor['valor']
                }
                channel.basic_publish(
                    exchange='leilao_vencedor_exchange',
                    routing_key='vencedor',
                    body=json.dumps(mensagem_vencedor)
                )
                print(f"[MS Lance] Vencedor do leilão {id_leilao} é {mensagem_vencedor['id_vencedor']}.")
            else:
                print(f"[MS Lance] Leilão {id_leilao} terminou sem lances.")
            del leiloes_ativos[id_leilao]
        
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=q_inicio.method.queue, on_message_callback=callback_leilao_iniciado)
    channel.basic_consume(queue='leilao_finalizado', on_message_callback=callback_leilao_finalizado)
    
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("[MS Lance] Consumidor interrompido.")
    finally:
        if connection and connection.is_open:
            connection.close()

if __name__ == '__main__':
    thread_rabbitmq = threading.Thread(target=iniciar_consumidor_rabbitmq, daemon=True)
    thread_rabbitmq.start()
    
    print("[MS Lance] Servidor Flask iniciado na porta 5002.")
    app.run(host='0.0.0.0', port=5002, debug=False)