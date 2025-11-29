import pika, requests, json, threading, time
from flask import Flask, request, jsonify 
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
PORT = 5003

RABBITMQ_HOST = 'localhost'

# Simulação do Sistema Externo de Pagamento
URL_SISTEMA_EXTERNO = "http://payment-system.com/api/payments" 

def publicar_evento(exchange_name, routing_key, payload):
    """ Função genérica para publicar um evento no RabbitMQ. """
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
        channel = connection.channel()
        
        channel.exchange_declare(exchange=exchange_name, exchange_type='direct')

        message = json.dumps(payload)
        channel.basic_publish(
            exchange=exchange_name,
            routing_key=routing_key,
            body=message,
            properties=pika.BasicProperties(
                delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE
            )
        )
        print(f"[MS Pagamento] Publicado evento '{routing_key}' para o exchange '{exchange_name}'.")
        connection.close()
    except Exception as e:
        print(f"[MS Pagamento] ERRO ao publicar evento {routing_key}: {e}")

def processar_leilao_vencedor(dados_vencedor):
    
    id_leilao = dados_vencedor.get('id_leilao')
    id_vencedor = dados_vencedor.get('id_vencedor')
    valor = dados_vencedor.get('valor') 

    print(f"[MS Pagamento] Processando vencedor do leilão {id_leilao} (Vencedor: {id_vencedor}, Valor: R$ {valor}).")

    # Simulação de Requisição REST ao Sistema Externo
    try:
        dados_pagamento = {
            "id_leilao": id_leilao,
            "id_cliente": id_vencedor,
            "valor": valor,
            "moeda": "BRL",
            # A URL do Webhook que o sistema externo usará para notificar
            "webhook_url": f"http://localhost:{PORT}/webhook_status" 
        }
        
        # Aponta para o arquivo local simulando o sistema externo, passando os dados necessários
        link_pagamento = f"http://localhost:8000/checkout.html?leilaoId={id_leilao}&clienteId={id_vencedor}&valor={valor}"
        print(f"[MS Pagamento] Link de pagamento gerado: {link_pagamento}")
        
        payload_link = {
            "id_leilao": id_leilao,
            "id_usuario": id_vencedor,
            "link": link_pagamento
        }
        
        publicar_evento(
            exchange_name='link_pagamento_exchange',
            routing_key='link_pagamento',
            payload=payload_link
        )
        
    except requests.exceptions.RequestException as e:
        print(f"[MS Pagamento] ERRO de comunicação com o sistema externo: {e}")

def callback_leilao_vencedor(ch, method, properties, body):
    dados = json.loads(body.decode('utf-8'))
    processar_leilao_vencedor(dados)
    ch.basic_ack(delivery_tag=method.delivery_tag)

def iniciar_consumidor_rabbitmq():
    print("[MS Pagamento] Conectando ao RabbitMQ...")
    connection = None
    channel = None

    while True:
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
            channel = connection.channel()
            print("[MS Pagamento] Conectado ao RabbitMQ!")
            break
        except pika.exceptions.AMQPConnectionError:
            print("[MS Pagamento] RabbitMQ indisponível. Tentando em 5s...")
            time.sleep(5)

    channel.exchange_declare(exchange='leilao_vencedor_exchange', exchange_type='direct')
    q_vencedor = channel.queue_declare(queue='', exclusive=True)
    channel.queue_bind(exchange='leilao_vencedor_exchange', queue=q_vencedor.method.queue, routing_key='vencedor')

    channel.basic_consume(
        queue=q_vencedor.method.queue,
        on_message_callback=callback_leilao_vencedor
    )

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("[MS Pagamento] Consumidor desligado.")
    finally:
        if connection and connection.is_open:
            connection.close()

# Endpoint Webhook
@app.route('/webhook_status', methods=['POST'])
def webhook_status():
    """
    Recebe a notificação assíncrona do sistema externo de pagamento.
    Publica o evento 'status_pagamento'.
    """
    try:
        dados_webhook = request.json
        if not dados_webhook:
            return jsonify({"erro": "Nenhum dado recebido"}), 400

        id_leilao = dados_webhook.get('id_leilao')
        id_usuario = dados_webhook.get('id_usuario')
        status = dados_webhook.get('status')
        
        print(f"[MS Pagamento - Webhook] Recebido status '{status}' para o Leilão {id_leilao}, Cliente {id_usuario}.")

        payload_status = {
            "id_leilao": id_leilao,
            "id_usuario": id_usuario,
            "status": status,
            "mensagem": f"Transação: {status}"
        }

        publicar_evento(
            exchange_name='status_pagamento_exchange',
            routing_key='status_pagamento',
            payload=payload_status
        )

        return jsonify({"status": "recebido e processado"}), 200

    except Exception as e:
        print(f"[MS Pagamento - Webhook] ERRO ao processar webhook: {e}")
        return jsonify({"erro": str(e)}), 500

if __name__ == '__main__':
    thread_rabbitmq = threading.Thread(target=iniciar_consumidor_rabbitmq, daemon=True)
    thread_rabbitmq.start()
    
    # Inicia o servidor Flask
    print(f"[MS Pagamento] Servidor Flask iniciado na porta {PORT}.")
    app.run(port=PORT, debug=False, threaded=True)