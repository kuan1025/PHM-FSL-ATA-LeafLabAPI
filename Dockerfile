# ---- base image ----
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# (opencv, skimage) common runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- deps ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- app ----
COPY . .

# default DB for compose (can be overridden)
ENV DATABASE_URL=postgresql+psycopg2://leaflab:leaflab@db:5432/leaflab

# set SAM checkpoint if you mount ./models
ENV SAM_MODEL_TYPE=vit_b
ENV SAM_CHECKPOINT=/app/models/sam_vit_b_01ec64.pth

EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
