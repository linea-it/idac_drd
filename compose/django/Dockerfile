# Estágio 1: build do frontend (React/MUI via Vite)
FROM node:22-slim AS frontend-build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json /src/frontend/
RUN cd frontend && npm ci
COPY frontend /src/frontend
RUN cd frontend && npm run build

# Estágio 2: Django (o bundle de frontend vem do estágio acima)
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev xmlsec1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ /app/requirements/
RUN pip install --no-cache-dir -r /app/requirements/local.txt

COPY . /app
COPY --from=frontend-build /src/idac_drd/static/frontend /app/idac_drd/static/frontend
RUN chmod +x /app/manage.py
