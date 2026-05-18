# Imagen base
FROM python:3.11-slim

# Evitar mensajes interactivos
ENV DEBIAN_FRONTEND=noninteractive
ENV ENV=cloud 
# Asegura que la salida de python se vea en los logs de Cloud Run
ENV PYTHONUNBUFFERED=True

# INSTALAR DEPENDENCIAS PARA PSYCOPG2, MAGIC Y WEASYPRINT
RUN apt-get update && \
    apt-get install -y \
    libmagic1 \
    gcc \
    libpq-dev \
    # Dependencias específicas para WeasyPrint:
    python3-pip python3-cffi python3-brotli libpango-1.0-0 \
    libharfbuzz0b libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libglib2.0-0 shared-mime-info && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar la aplicación
COPY . .

# Exponer el puerto
EXPOSE 8080

# Comando de ejecución con timeout extendido para generación de PDFs
CMD ["gunicorn", "main:flask_app", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "0"]
