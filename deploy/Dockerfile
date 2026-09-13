# ---- frontend build
FROM node:22-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- backend runtime
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    F1LAPS_DATA_DIR=/data \
    F1LAPS_STATIC_DIR=/app/static
WORKDIR /app
RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown app:app /data
COPY backend/pyproject.toml ./
COPY backend/f1laps ./f1laps
RUN pip install --no-cache-dir . && rm -rf /root/.cache
COPY --from=frontend /src/dist ./static
USER app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"
CMD ["uvicorn", "f1laps.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
