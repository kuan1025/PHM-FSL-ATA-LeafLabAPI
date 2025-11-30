FROM python:3.11-slim
WORKDIR /grabcut_worker
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    libglib2.0-0 \
    libgl1 \
  && rm -rf /var/lib/apt/lists/*

COPY grabcut_worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY grabcut_worker/ /grabcut_worker
COPY app/ /app
RUN chmod +x /grabcut_worker/bootstrap.sh
ENV PYTHONPATH=/app
CMD ["/grabcut_worker/bootstrap.sh"]
