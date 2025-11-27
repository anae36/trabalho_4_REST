# Usa uma imagem base Python 3.11 leve
FROM python:3.11-slim

# Define o diretório de trabalho dentro do container
WORKDIR /usr/src/app

# Copia o arquivo de requisitos e instala as dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código da aplicação
COPY . .

# Define a porta que a aplicação Flask irá expor
EXPOSE 3000

# Comando para iniciar a aplicação (ajuste se o seu arquivo principal tiver outro nome)
CMD ["python", "backend/api.py"]