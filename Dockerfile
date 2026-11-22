# Container image for flood to policy (Streamlit map, JSON API, MCP tools, tests).
#
# Why a container: on the Windows host an application-control policy blocks the
# native DLLs of rasterio, pyogrio, rasterstats and tiktoken, so the geospatial half
# runs in Linux. The manylinux wheels bundle their own GDAL/PROJ, so
# python:3.12-slim + `pip install -r requirements.txt` is the whole stack (no apt GDAL).
# Fallback if a wheel is missing: --build-arg BASE_IMAGE=ghcr.io/osgeo/gdal:ubuntu-small-3.9.2
# (system Python, so pip needs --break-system-packages; not the tested path).
#
# Targets:
#   app       code + the four small files of data/processed/; bind-mount the rest of data/.
#   test      app + pytest (requirements-test.txt) + tests/.
#   portable  app + the whole data tree, for a machine that has never seen this repo.
#             Last on purpose: a bare `docker build .` produces it.
#
# No secrets: .env is excluded in .dockerignore and the source is copied path by
# path, never `COPY . .`. API keys and RDH_BEARER_TOKEN (valid 10 h) arrive at run time.

# The default base is the `python-base` stage so Dependabot can read a literal FROM
# line; --build-arg BASE_IMAGE=<image> replaces it.
ARG BASE_IMAGE=python-base

FROM python:3.12-slim AS python-base

# --- React UI build -------------------------------------------------------------
# web/dist is gitignored, so this stage builds it; only the static files reach the
# final image. api/main.py serves web/dist at / on port 8001.
# `npm run build` first copies ../data/processed/event_2021_web.json into web/public/.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
COPY data/processed/event_2021_web.json /data/processed/event_2021_web.json
RUN npm run build

FROM ${BASE_IMAGE} AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_HEADLESS=true

WORKDIR /app

# Dependency layer first, so a code edit does not reinstall geopandas.
COPY requirements.txt .
# libexpat1: needed by the pyogrio/GDAL wheels at import, absent from python:3.12-slim.
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*
RUN pip install -r requirements.txt

# Unprivileged user; owns data/ so a bind mount and the RDH cache inherit it.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data/raw /app/data/processed \
    && chown -R app:app /app/data

# Source, path by path: data/ must stay in the build context for `portable`, and
# `COPY . .` would pull it into this stage too.
COPY --chown=app:app src/ ./src/
COPY --chown=app:app app/ ./app/
COPY --chown=app:app api/ ./api/
COPY --chown=app:app config/ ./config/
COPY --chown=app:app scripts/ ./scripts/
# The Streamlit "AI log" tab appends to docs/ai_usage_log.md; owned by `app` so it stays writable.
COPY --chown=app:app docs/ ./docs/
COPY --chown=app:app README.md pytest.ini ./
# web/ carries the Vite sources; web/dist comes from the `web` stage.
COPY --chown=app:app web/ ./web/
COPY --from=web --chown=app:app /web/dist ./web/dist
# bi/: Power BI project text definitions (bi/data/ is excluded in .dockerignore).
COPY --chown=app:app bi/ ./bi/
# The four files committed under data/processed/: the frozen tables, the July 2021
# story and the licence notice. A bind mount of data/ hides them.
COPY --chown=app:app data/processed/DATA_NOTICE.md data/processed/event_2021_web.json \
     data/processed/exposure.parquet data/processed/context.parquet ./data/processed/

USER app

EXPOSE 8501 8001

# Streamlit (default CMD, 8501) or the API (uvicorn, 8001): healthy if either answers.
# Probed with python because the slim image ships no curl.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request as r; r.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=2)" \
     || python -c "import urllib.request as r; r.urlopen('http://127.0.0.1:8001/api/health', timeout=2)"

CMD ["python", "-m", "streamlit", "run", "app/streamlit_app.py", \
     "--server.port=8501", "--server.address=0.0.0.0"]


# --- Test image: app + pytest + the suite ---------------------------------------
FROM app AS test
COPY requirements-test.txt .
USER root
RUN pip install -r requirements-test.txt
USER app
COPY --chown=app:app tests/ ./tests/
CMD ["python", "-m", "pytest", "-q"]

# --- The self-contained image ---------------------------------------------------
# App plus the corpus and rasters (as large as data/). `*.part` files are excluded
# in .dockerignore so a half-downloaded raster cannot be baked in.
FROM app AS portable
COPY --chown=app:app data/ ./data/
