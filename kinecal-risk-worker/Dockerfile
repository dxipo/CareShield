FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY kinecal-risk-worker/app ./app
COPY kinecal-risk-worker/config /opt/careshield/kinecal-config

EXPOSE 8092

# The PyTorch/CUDA runtime is independently mounted so this research model
# cannot change the MotionCLIP or realtime fall-detection environments.
CMD ["/runtime/kinecal/bin/python", "-m", "app.main"]
