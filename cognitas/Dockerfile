# Usamos Python 3.12 versión "slim" (más ligera)
FROM python:3.12-slim

# Evita que Python genere archivos .pyc y permite ver logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instalamos tzdata para que funcionen bien las zonas horarias del sistema
RUN apt-get update && \
    apt-get install -y tzdata && \
    rm -rf /var/lib/apt/lists/*

# Directorio de trabajo dentro del contenedor
WORKDIR /app

# 1. Copiamos primero los requirements para aprovechar la caché de Docker
COPY requirements.txt .

# 2. Instalamos las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copiamos el resto del código
COPY . .

# Comando de inicio
CMD ["python", "-m", "cognitas.bot"]