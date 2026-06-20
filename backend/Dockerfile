FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
ENV PIP_DEFAULT_TIMEOUT=2000
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --default-timeout=2000 --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Use Gunicorn as the production process manager with Uvicorn async workers for high concurrency
CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--chdir", "."]