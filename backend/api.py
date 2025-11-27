import pika, requests, json, threading, time
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sse import sse

# python -m http.server 8000

# --- Configuração do Flask ---
app = Flask(__name__)
CORS(app)

# O hostname é 'redis', conforme definido no docker-compose.yml
app.config["REDIS_URL"] = "redis://localhost:6379" 
app.register_blueprint(sse, url_prefix='/stream')

# --- URLs dos Microsserviços ---
MS_LEILAO_URL = "http://localhost:5001"
MS_LANCE_URL = "http://localhost:5002"

# --- Gerenciamento de Estado Interno do Gateway ---

# 1. Dicionário de "Interesses":
#    Guarda quais clientes estão ouvindo quais leilões.
#    Formato: {"id_leilao": {set_de_clientes}}
interesses = {}

# O Flask-SSE/Redis gerencia as conexões e o envio.

# Mutex para proteger o acesso concorrente ao dicionário de interesses
lock = threading.Lock()

# --- 1. Endpoints REST (Proxy para Microsserviços) ---

@app.route('/leiloes', methods=['POST'])
def criar_leilao():
    """ Repassa a criação de leilão para o MS Leilão """
    try:
        # Repassa o JSON recebido diretamente
        response = requests.post(f"{MS_LEILAO_URL}/leiloes", json=request.json)
        # Retorna a resposta do microsserviço (corpo e status)
        return response.content, response.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"erro": "MS Leilão está offline"}), 503

@app.route('/leiloes', methods=['GET'])
def consultar_leiloes():
    """ Repassa a consulta de leilões para o MS Leilão """
    try:
        response = requests.get(f"{MS_LEILAO_URL}/leiloes")
        return response.content, response.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"erro": "MS Leilão está offline"}), 503

@app.route('/lances', methods=['POST'])
def efetuar_lance():
    """ Repassa o lance para o MS Lance """
    try:
        dados = request.json
        if 'id_usuario' not in dados:
             return jsonify({"erro": "id_usuario é obrigatório"}), 400
        
        response = requests.post(f"{MS_LANCE_URL}/lances", json=dados)
        return response.content, response.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"erro": "MS Lance está offline"}), 503

# --- 2. Endpoints REST (Gerenciamento de Interesse) ---

@app.route('/notificacoes/<id_leilao>', methods=['POST'])
def registrar_interesse(id_leilao):
    """ O cliente (frontend) registra interesse em um leilão """
    dados = request.json
    cliente_id = str(dados.get('id_usuario'))
    if not cliente_id:
        return jsonify({"erro": "id_usuario é obrigatório"}), 400
    
    with lock:
        if id_leilao not in interesses:
            interesses[id_leilao] = set()
        interesses[id_leilao].add(cliente_id)
        
    print(f"[Gateway] Cliente '{cliente_id}' registrou interesse no leilão '{id_leilao}'.")
    # O frontend deve se conectar a /eventos/stream?channel=<id_leilao>
    return jsonify({"status": "registrado", "leilao": id_leilao, "cliente": cliente_id, "canal": id_leilao}), 200

@app.route('/notificacoes/<id_leilao>', methods=['DELETE'])
def cancelar_interesse(id_leilao):
    """ O cliente (frontend) cancela o interesse em um leilão """
    dados = request.json
    cliente_id = str(dados.get('id_usuario'))
    if not cliente_id:
        return jsonify({"erro": "id_usuario é obrigatório"}), 400

    with lock:
        if id_leilao in interesses and cliente_id in interesses[id_leilao]:
            interesses[id_leilao].remove(cliente_id)
            if not interesses[id_leilao]: # Se o set ficar vazio
                del interesses[id_leilao]

    print(f"[Gateway] Cliente '{cliente_id}' cancelou interesse no leilão '{id_leilao}'.")
    return jsonify({"status": "cancelado", "leilao": id_leilao, "cliente": cliente_id}), 200

# --- 3. Funções Auxiliares de Notificação (com sse.publish) ---

def notificar_clientes_interessados(id_leilao, evento_nome, payload):
    with lock:
        # IMPORTANTE: Cria o contexto da aplicação para acessar o Redis
        with app.app_context():
            if id_leilao in interesses:
                lista_clientes = interesses[id_leilao]
                print(f"[Gateway Notification] Notificando {len(lista_clientes)} clientes sobre {evento_nome}...", flush=True)
                
                for cliente_id in lista_clientes:
                    try:
                        sse.publish(payload, type=evento_nome, channel=str(cliente_id))
                    except Exception as e:
                        print(f"[ERRO SSE] Falha ao enviar para {cliente_id}: {e}")
            else:
                print(f"[Gateway Notification] Ninguém interessado no leilão {id_leilao} para evento {evento_nome}.")


def notificar_cliente_direto(cliente_id, evento_nome, payload):
    with lock:
        # IMPORTANTE: Cria o contexto da aplicação para acessar o Redis
        with app.app_context():
            print(f"[Gateway Notification] Notificando direto: {cliente_id} - Evento: {evento_nome}")
            try:
                sse.publish(payload, type=evento_nome, channel=str(cliente_id))
            except Exception as e:
                print(f"[ERRO SSE] Falha direta para {cliente_id}: {e}")

# --- 4. Consumidor RabbitMQ (em Thread separada) ---

def iniciar_consumidor_rabbitmq():
    """ Roda em uma thread para ouvir o RabbitMQ """
    print("[Gateway] Iniciando consumidor RabbitMQ em thread separada...")
    
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
    channel = connection.channel()

    # --- Declaração das filas que o Gateway vai OUVIR ---
    
    # Evento: lance_validado
    channel.exchange_declare(exchange='lance_validado_exchange', exchange_type='direct')
    q_lance_valido = channel.queue_declare(queue='', exclusive=True)
    channel.queue_bind(exchange='lance_validado_exchange', queue=q_lance_valido.method.queue, routing_key='lance_valido')

    # Evento: lance_invalidado
    channel.exchange_declare(exchange='lance_invalidado_exchange', exchange_type='direct')
    q_lance_invalido = channel.queue_declare(queue='', exclusive=True)
    channel.queue_bind(exchange='lance_invalidado_exchange', queue=q_lance_invalido.method.queue, routing_key='lance_invalido')

    # Evento: leilao_vencedor
    channel.exchange_declare(exchange='leilao_vencedor_exchange', exchange_type='direct')
    q_vencedor = channel.queue_declare(queue='', exclusive=True)
    channel.queue_bind(exchange='leilao_vencedor_exchange', queue=q_vencedor.method.queue, routing_key='vencedor')
    
    # Evento: link_pagamento
    channel.exchange_declare(exchange='link_pagamento_exchange', exchange_type='direct')
    q_link = channel.queue_declare(queue='', exclusive=True)
    channel.queue_bind(exchange='link_pagamento_exchange', queue=q_link.method.queue, routing_key='link_pagamento')

    # Evento: status_pagamento
    channel.exchange_declare(exchange='status_pagamento_exchange', exchange_type='direct')
    q_status = channel.queue_declare(queue='', exclusive=True)
    channel.queue_bind(exchange='status_pagamento_exchange', queue=q_status.method.queue, routing_key='status_pagamento')
    
    # --- Callbacks do Consumidor ---
    
    def callback_lance_validado(ch, method, properties, body):
        dados = json.loads(body.decode('utf-8'))
        id_leilao = str(dados.get('id_leilao'))
        
        # Print de Debug
        print(f"[Gateway RabbitMQ] >>> RECEBIDO 'lance_validado' do Leilão {id_leilao}. Acionando SSE...", flush=True)
        
        notificar_clientes_interessados(id_leilao, "novo_lance", dados)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def callback_lance_invalidado(ch, method, properties, body):
        dados = json.loads(body.decode('utf-8'))
        cliente_id = str(dados.get('id_usuario'))
        print(f"[Gateway RabbitMQ] Recebido: 'lance_invalidado' para usuário {cliente_id}")
        # Notifica APENAS o cliente usando sse.publish()
        notificar_cliente_direto(cliente_id, "lance_invalido", dados)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    def callback_leilao_vencedor(ch, method, properties, body):
        dados = json.loads(body.decode('utf-8'))
        id_leilao = str(dados.get('id_leilao'))
        print(f"[Gateway RabbitMQ] Recebido: 'leilao_vencedor' para leilão {id_leilao}")
        
        # Notifica TODOS os interessados sobre o vencedor usando sse.publish()
        notificar_clientes_interessados(id_leilao, "leilao_vencedor", dados)
        
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def callback_link_pagamento(ch, method, properties, body):
        dados = json.loads(body.decode('utf-8'))
        cliente_id = str(dados.get('id_usuario')) # O vencedor
        print(f"[Gateway RabbitMQ] Recebido: 'link_pagamento' para usuário {cliente_id}")
        # Notifica APENAS o vencedor usando sse.publish()
        notificar_cliente_direto(cliente_id, "link_pagamento", dados) 
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def callback_status_pagamento(ch, method, properties, body):
        dados = json.loads(body.decode('utf-8'))
        cliente_id = str(dados.get('id_usuario'))
        print(f"[Gateway RabbitMQ] Recebido: 'status_pagamento' para usuário {cliente_id}")
        # Notifica APENAS o cliente usando sse.publish()
        notificar_cliente_direto(cliente_id, "status_pagamento", dados) 
        ch.basic_ack(delivery_tag=method.delivery_tag)

    # --- Inicia os consumidores ---
    channel.basic_consume(queue=q_lance_valido.method.queue, on_message_callback=callback_lance_validado)
    channel.basic_consume(queue=q_lance_invalido.method.queue, on_message_callback=callback_lance_invalidado)
    channel.basic_consume(queue=q_vencedor.method.queue, on_message_callback=callback_leilao_vencedor)
    channel.basic_consume(queue=q_link.method.queue, on_message_callback=callback_link_pagamento)
    channel.basic_consume(queue=q_status.method.queue, on_message_callback=callback_status_pagamento)

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()

# --- Inicialização ---
if __name__ == '__main__':
    # 1. Inicia o consumidor RabbitMQ em uma thread daemon
    thread_rabbitmq = threading.Thread(target=iniciar_consumidor_rabbitmq, daemon=True)
    thread_rabbitmq.start()
    
    # 2. Inicia o servidor Flask (porta 3000)
    #    'threaded=True' é crucial para o Flask gerenciar múltiplas
    #    conexões SSE e REST simultaneamente.
    print("[Gateway] Servidor Flask iniciado na porta 3000.")
    app.run(host='0.0.0.0', port=3000, debug=False, threaded=True)
