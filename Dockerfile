FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY config.yml ./config.yml
COPY demo_consumer.py ./demo_consumer.py

ENV PYTHONPATH=/app

CMD ["python", "-m", "app.cli", "api"]
