# ============================================
# Aguacol Asistencia — imagen de la app (PostgreSQL vía docker-compose)
# ============================================
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Santiago

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

# Dependencias primero: la capa se cachea mientras requirements no cambie
COPY requirements-cloud.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/

RUN mkdir -p downloads logs     && useradd --uid 1000 --create-home --shell /usr/sbin/nologin app     && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'),timeout=4)" || exit 1

CMD exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
