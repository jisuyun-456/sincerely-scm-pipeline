FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends fonts-nanum && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r api/requirements.txt

EXPOSE 8080
CMD uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-8080}
