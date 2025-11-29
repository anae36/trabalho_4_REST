import pika, time, datetime, json
from flask import Flask, request, jsonify
import threading

app = Flask(__name__)

leiloes = []
leilao_id_counter = 1

@app.route('/leiloes', methods=['POST'])
def criar_leilao():
    global leilao_id_counter
    dados = request.json
    
    try:
        novo_leilao = {
            "id": leilao_id_counter,
            "produto": dados['produto'],
            "descricao": dados['descricao'],
            "valor_inicial": float(dados['valor_inicial']),
            "hora_inicio": datetime.datetime.fromisoformat(dados['hora_inicio']),
            "hora_fim": datetime.datetime.fromisoformat(dados['hora_fim']),
            "status": "Pendente"
        }
        leiloes.append(novo_leilao)
        leilao_id_counter += 1
        print(f"[MS Leilão] Leilão '{novo_leilao['produto']}' criado com ID {novo_leilao['id']}.")
        return jsonify(novo_leilao), 201
    
    except Exception as e:
        print(f"[MS Leilão] Erro ao criar leilão: {e}")
        return jsonify({"erro": "Dados inválidos"}), 400
    
@app.route('/leiloes', methods=['GET'])
def consultar_leiloes():
    agora = datetime.datetime.now(datetime.timezone.utc)

    leiloes_ativos = [
        leilao for leilao in leiloes 
        if leilao['status'] == 'Ativo'
    ]
    
    leiloes_para_json = []
    for leilao in leiloes_ativos:
        leiloes_para_json.append({
            "id": leilao['id'],
            "produto": leilao['produto'],
            "descricao": leilao['descricao'],
            "valor_inicial": leilao['valor_inicial'],
            "hora_inicio": leilao['hora_inicio'].isoformat(),
            "hora_fim": leilao['hora_fim'].isoformat(),
        })
        
    return jsonify(leiloes_para_json)

def iniciar_publicador_rabbitmq():
    
    print("[MS Leilão] Iniciando thread do Publicador...")
    
    while True: 
        connection = None
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
            channel = connection.channel()
            
            # Declara as exchanges
            channel.exchange_declare(exchange='leilao_inicio_exchange', exchange_type='fanout')
            channel.exchange_declare(exchange='leilao_fim_exchange', exchange_type='direct')
            channel.queue_declare(queue='leilao_finalizado')
            channel.queue_bind(exchange='leilao_fim_exchange', queue='leilao_finalizado', routing_key='black')
            
            print("[MS Leilão] Publicador conectado e rodando!")

            while True:
                hora_atual = datetime.datetime.now(datetime.timezone.utc)
                for leilao in list(leiloes): 
                    if leilao['status'] == 'Pendente' and leilao['hora_inicio'] <= hora_atual:
                        leilao['status'] = 'Ativo'
                        mensagem = {
                            "id_leilao": leilao['id'],
                            "descricao": leilao['descricao'],
                            "valor_inicial": leilao['valor_inicial'],
                            "hora_inicio": leilao['hora_inicio'].isoformat()
                        }
                        channel.basic_publish(exchange='leilao_inicio_exchange', routing_key='', body=json.dumps(mensagem))
                        print(f"[MS Leilão] Leilão {leilao['id']} INICIADO (Enviado RabbitMQ).")
                    
                    elif leilao['status'] == 'Ativo' and leilao['hora_fim'] <= hora_atual:
                        leilao['status'] = 'Encerrado'
                        mensagem = {
                            "id_leilao": leilao['id'],
                            "hora_fim": leilao['hora_fim'].isoformat()
                        }
                        channel.basic_publish(exchange='leilao_fim_exchange', routing_key='black', body=json.dumps(mensagem))
                        print(f"[MS Leilão] Leilão {leilao['id']} FINALIZADO (Enviado RabbitMQ).")
                
                time.sleep(1) 
        
        except (pika.exceptions.AMQPConnectionError, pika.exceptions.StreamLostError, Exception) as e:
            print(f"[MS Leilão] Conexão perdida: {e}. Reconectando em 5s...")
            time.sleep(5)
        
        finally:
            if connection and connection.is_open:
                try:
                    connection.close()
                except:
                    pass

if __name__ == '__main__':
    thread_rabbitmq = threading.Thread(target=iniciar_publicador_rabbitmq, daemon=True)
    thread_rabbitmq.start()
    
    print("[MS Leilão] Servidor Flask iniciado na porta 5001.")
    app.run(host='0.0.0.0', port=5001, debug=False)



