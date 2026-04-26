FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    DATA_DIR=/app/data/

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN apt-get update && \
    apt-get install -y --no-install-recommends gosu && \
    rm -rf /var/lib/apt/lists/*

COPY src ./src
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN useradd -m -u 10001 appuser && \
    mkdir -p "${DATA_DIR}" && \
    chown -R appuser:appuser "${DATA_DIR}" && \
    chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8080\")}/health').read()" || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${PORT} src.handler_openai:app --workers 2 --threads 8 --timeout 120"]
