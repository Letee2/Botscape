# Dockerfile
FROM python:3.12-slim-bookworm

WORKDIR /app


COPY requirements.txt .

RUN apt-get update && apt-get install -y \
    build-essential \
    libfuzzy-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

COPY . .


ENV PYTHONPATH=/app

CMD ["python", "-m", "botscape.services.listener.main"]