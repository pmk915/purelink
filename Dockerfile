FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      curl \
      espeak-ng \
      ffmpeg \
      fonts-dejavu-core \
      tesseract-ocr \
      tesseract-ocr-eng \
      unzip && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY docs ./docs
COPY scripts ./scripts
COPY README.md ./README.md

RUN mkdir -p /opt/vosk && \
    curl -fsSL https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -o /tmp/vosk-model.zip && \
    unzip -q /tmp/vosk-model.zip -d /opt/vosk && \
    rm -f /tmp/vosk-model.zip

RUN mkdir -p data/uploads data/parsed data/chunks data/vector_store logs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
