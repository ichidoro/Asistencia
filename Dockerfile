# ============================================
# Aguacol Asistencia — Google Cloud Run
# ============================================
FROM python:3.13-slim

# Variables de entorno para Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias Python
COPY requirements-cloud.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY backend/ backend/
COPY frontend/ frontend/
COPY Productos.xlsx .

# Crear directorios necesarios
RUN mkdir -p data/downloads data/local_db logs

# Puerto (Cloud Run define $PORT=8080)
EXPOSE 8080

# Usar uvicorn directamente con $PORT de Cloud Run
CMD exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}
