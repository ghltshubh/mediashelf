# MediaShelf — one image, one container, one process.
# Stage 1: build the React SPA. Stage 2: Python runtime serving API + static bundle.

FROM node:22-alpine AS web
WORKDIR /build
COPY app/web/package.json app/web/package-lock.json ./
RUN npm ci
COPY app/web ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /srv

# Dependencies install against a stub package, BEFORE the source is copied, so
# editing app/ doesn't invalidate this layer. It is by far the most expensive
# one: under QEMU for arm64, any C extension without a prebuilt aarch64 wheel
# compiles from source, which is minutes each. Copying app/ first (as this once
# did) meant every release rebuilt all of it.
COPY pyproject.toml README.md ./
RUN mkdir -p app && touch app/__init__.py \
 && pip install --no-cache-dir . \
 && pip uninstall -y mediashelf \
 && rm -rf app

# Now the parts that change every commit — cheap layers on top of a cached one.
COPY app ./app
COPY --from=web /build/dist ./app/web/dist

# Optional: bake in the yt-dlp metadata plugin (zero-quota YouTube search).
# Deliberately OFF by default — yt-dlp is a detected, user-opted plugin (plan
# Appendix B) and never ships in official images. Opt in with:
#   docker compose build --build-arg INCLUDE_YTDLP=1
ARG INCLUDE_YTDLP=0
RUN if [ "$INCLUDE_YTDLP" = "1" ]; then pip install --no-cache-dir yt-dlp; fi

ENV MEDIASHELF_DATA_DIR=/data
VOLUME /data
EXPOSE 8000

# Liveness: the API's /api/health endpoint (no external deps, no key required).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
