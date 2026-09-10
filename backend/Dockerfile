# syntax=docker/dockerfile:1.7
FROM python:3.14.5-alpine3.22@sha256:6b91e66ab2a880ce9ca5a1b91c70f45963ff71ff68268df056336e1a657d5efd AS runtime
LABEL org.opencontainers.image.source="https://github.com/dlamaro96/recordlane" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="0.1.0-alpha.3"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apk upgrade --no-cache
RUN addgroup -S -g 10001 recordlane && adduser -S -D -H -u 10001 -G recordlane recordlane
WORKDIR /app
COPY pyproject.toml README.md ./
RUN pip install \
    fastapi==0.141.1 uvicorn==0.35.0 pydantic==2.13.5 pydantic-settings==2.11.0 \
    SQLAlchemy==2.0.52 'psycopg[binary]==3.3.5' PyYAML==6.0.3 httpx==0.28.1 \
    python-multipart==0.0.31 cryptography==50.0.0 'PyJWT[crypto]==2.13.0' \
    prometheus-client==0.22.1 opentelemetry-api==1.44.0 opentelemetry-sdk==1.44.0 \
    opentelemetry-exporter-otlp-proto-http==1.44.0 \
    opentelemetry-instrumentation-fastapi==0.65b0 pyarrow==25.0.1
COPY src ./src
RUN pip install --no-deps .
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=3s --retries=5 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live')"]
CMD ["uvicorn", "recordlane.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
