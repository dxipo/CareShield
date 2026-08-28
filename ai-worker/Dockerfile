FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/shared/python \
    YOLO_CONFIG_DIR=/models/ultralytics-config \
    TORCH_HOME=/models/torch-cache

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY ai-worker/requirements-gpu.txt ./requirements-gpu.txt
COPY ai-worker/requirements.txt ./requirements.txt
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu130
RUN pip install --no-cache-dir --index-url "${PYTORCH_INDEX_URL}" --extra-index-url "${PIP_INDEX_URL}" -r requirements-gpu.txt \
    && pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt

COPY shared/python /shared/python
COPY ai-worker/app ./app

RUN mkdir -p /models

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
