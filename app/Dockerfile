# ─────────────────────────────────────────────
# LeafLab API  CMD
# docker build -t leaflab-api:dev ./app
# docker build --platform=linux/amd64 -t leaflab-api:latest ./app
# ─────────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1


RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for better caching
COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Defaults (can be overridden at runtime)
ENV DATABASE_URL=postgresql+psycopg2://leaflab:leaflab@db:5432/leaflab
ENV JWT_SECRET=be863bd931ebb503918887dec9efac55
ENV SAM_MODEL_TYPE=vit_b
ENV SAM_CHECKPOINT=/app/models/sam_vit_b_01ec64.pth

# Behavior toggles:
ENV RELOAD=0
ENV ROOT_PATH=""

EXPOSE 8001

# Use shell expansion to conditionally add flags (no extra entrypoint file needed)
CMD ["sh","-lc", "uvicorn main:app --host 0.0.0.0 --port 8000 ${ROOT_PATH:+--root-path $ROOT_PATH} ${RELOAD:+--reload}"]
