FROM python:3.13.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt \
    && groupadd --system app \
    && useradd --system --gid app --create-home app \
    && apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

COPY --chown=app:app main.py .
COPY --chown=app:app langs ./langs
COPY --chown=app:app data/tarifs.json ./data/tarifs.json

CMD ["python", "main.py"]

EXPOSE 2005
HEALTHCHECK --interval=1h --timeout=5s --start-period=20s --retries=3 CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:2005/api/v1/health', timeout=3)" || exit 1
