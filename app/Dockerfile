# ─────────────────────────────────────────────
# LeafLab API
# build:
#   docker build -t leaflab-api:dev ./
#   docker build --platform=linux/amd64 -t leaflab-api:latest ./
# ─────────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1


RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libpq5 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app


COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000


CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
