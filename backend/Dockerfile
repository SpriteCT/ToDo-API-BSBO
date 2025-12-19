FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app/backend

RUN apt-get update && apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/. .

# Порт по умолчанию (можно переопределить через переменную окружения PORT)
ARG DEFAULT_PORT=8000
EXPOSE ${DEFAULT_PORT}

# Порт и хост можно переопределить через переменные окружения PORT и HOST
CMD ["sh", "-c", "uvicorn main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000}"]


