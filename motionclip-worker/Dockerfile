FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY motionclip-worker/app ./app

EXPOSE 8091

# PyTorch remains in an isolated, operator-provided runtime. This image
# deliberately does not copy the 6.5 GB environment or the 216 MB research
# checkpoint into Git/build context.
CMD ["/runtime/motionclip/bin/python", "-m", "app.main"]
