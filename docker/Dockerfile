# MediaShelf — one image, one container, one process.
# Stage 1: build the React SPA. Stage 2: Python runtime serving API + static bundle.

FROM node:22-alpine AS web
WORKDIR /build
COPY app/web/package.json app/web/package-lock.json ./
RUN npm ci
COPY app/web ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /srv
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY --from=web /build/dist ./app/web/dist

ENV MEDIASHELF_DATA_DIR=/data
VOLUME /data
EXPOSE 8000

# Liveness: the API's /api/health endpoint (no external deps, no key required).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
