FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/shared/python

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY fall-risk-worker/requirements.txt ./requirements.txt
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt

COPY fall-risk-worker/pipelines/visionmd/requirements.txt /tmp/visionmd-requirements.txt
RUN python -m venv /opt/visionmd-env \
    && /opt/visionmd-env/bin/pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" \
       -r /tmp/visionmd-requirements.txt

COPY third_party/GVHMR /opt/gvhmr
# Upstream imports turtle.forward although it is unused. Importing turtle
# pulls Tk into a headless service and prevents GVHMR startup on slim images.
RUN sed -i '/^from turtle import forward$/d' \
    /opt/gvhmr/hmr4d/utils/body_model/body_model.py

COPY shared/python /shared/python
COPY fall-risk-worker/app ./app
COPY fall-risk-worker/pipelines/visionmd /opt/visionmd-app
COPY fall-risk-worker/pipelines/gvhmr /opt/careshield/gvhmr

RUN mkdir -p /data/fall-risk /models/fall-risk /opt/gvhmr/inputs/checkpoints

EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090", "--no-access-log"]
