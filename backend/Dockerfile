FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements /tmp/requirements

RUN pip install --upgrade pip \
    && pip install -r /tmp/requirements/production.txt

COPY backend /app
COPY docker/backend/start-web.sh /app/docker/backend/start-web.sh

RUN chmod +x /app/docker/backend/start-web.sh

EXPOSE 8000

