FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY migrations ./migrations
COPY scripts ./scripts
RUN python -m pip install --no-cache-dir ".[postgres,s3,redis,http]"

RUN useradd --create-home --shell /usr/sbin/nologin scenara_data \
    && chown -R scenara_data:scenara_data /app
USER scenara_data

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/health', timeout=3)"]

CMD ["uvicorn", "scenara_data.api.app:app", "--host", "0.0.0.0", "--port", "8081"]
