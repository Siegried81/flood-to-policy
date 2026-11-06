# Container image for flood to policy (Streamlit map, JSON API, CLI, tests).
#
# This image is not a packaging nicety here, it is how the geospatial half of the
# kit runs at all. On the Windows host, `rasterio`, `pyogrio`, `rasterstats` and
# `tiktoken` all fail at import: an application-control policy blocks the native
# DLLs the wheels ship ("Une strategie de controle d'application a bloque ce
# fichier", and GDAL therefore never lands on PATH). Nothing in the Python layer
# can work around that, so every zonal statistic, every vector read and every
# token count has to happen inside Linux.
#
# **Why pip wheels and not a GDAL base image.** That blocked-DLL failure is a
# host policy, not a missing GDAL: `rasterio`, `pyogrio` and `rasterstats`
# publish manylinux wheels with their own GDAL/PROJ shared objects bundled, and
# those load normally on Debian. So `python:3.12-slim` plus `pip install -r
# requirements.txt` is the whole geospatial stack, with no apt-get GDAL to keep
# in step with the wheels - which is the classic way to end up with two GDALs
# and a segfault. If a wheel ever goes missing for a platform, the escape hatch
# is one build argument rather than a rewrite:
#
#   docker build --build-arg BASE_IMAGE=ghcr.io/osgeo/gdal:ubuntu-small-3.9.2 .
#
# (that base ships a system Python, so pip then needs
# `--break-system-packages`; it is a fallback, not the tested path.)
#
# **Two stages, because the data is far bigger than the code**: 83 GiB measured
# 2026-11-05, 70 GiB of it HERA river discharge. `app` holds the code and the
# four small files committed under data/processed/, and expects the rest of
# `data/` to be bind-mounted - that is the day-to-day image, rebuilt in
# seconds. `portable` is `app` with the whole data tree copied in, which is the
# image that fits on a USB stick and runs the demo on a machine that has never
# seen this repo. `portable` is last, so a bare `docker build .` produces the
# self-contained one; `--target app` asks for the small one. See
# docker-compose.yml for which service uses which.
#
# **No secrets, ever.** `.env` is excluded in .dockerignore and the source is
# copied path by path rather than with `COPY . .`, so a key cannot arrive by
# accident. `GROQ_API_KEY` is passed at run time, and `RDH_BEARER_TOKEN` can
# only ever be passed at run time: it expires after 10 hours, so a token baked
# into an image is dead before the image is useful.

ARG BASE_IMAGE=python:3.12-slim

# --- React UI build -------------------------------------------------------------
# web/dist is gitignored, so a fresh clone, and the publish runner, has no build
# of the React UI. This stage makes one. Only the static files reach the final
# image, not Node: api/main.py serves web/dist at / on port 8010.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
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

# Dependency layer first, so editing a Python file rebuilds only the cheap
# layers below instead of reinstalling geopandas and friends.
COPY requirements.txt .
# libexpat1 is the one system library the manylinux wheels of pyogrio/GDAL
# load at import time that python:3.12-slim does not ship. Without it the
# image builds, and `import pyogrio` fails with `libexpat.so.1: cannot open
# shared object file` - which is what the CI docker job measured on the
# first run, while a build on the GDAL base image hid it.
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*
RUN pip install -r requirements.txt

# Unprivileged user. data/ is created and owned by it so a bind mount and the
# RDH cache written underneath it both inherit that ownership.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data/raw /app/data/processed \
    && chown -R app:app /app/data

# Source, path by path rather than `COPY . .`: data/ has to stay in the build
# context for the `portable` stage below, and a wholesale copy would then pull
# the whole data tree into this stage too. Being explicit also means a new file at the repo
# root cannot silently end up in the image.
COPY --chown=app:app src/ ./src/
COPY --chown=app:app app/ ./app/
COPY --chown=app:app api/ ./api/
COPY --chown=app:app config/ ./config/
COPY --chown=app:app scripts/ ./scripts/
# The Streamlit "AI log" tab creates and appends to docs/ai_usage_log.md, and the
# docs-numbers and legislation tests read README.md and docs/. Owned by `app` so
# the log stays writable. pytest.ini carries the suite's warning filter.
COPY --chown=app:app docs/ ./docs/
COPY --chown=app:app README.md pytest.ini ./
# Tests travel with the image on purpose: "pytest green with the Wi-Fi off" is a
# line on the day-of checklist, and on this host it can only be run in here.
COPY --chown=app:app tests/ ./tests/
# web/ carries the Vite sources; web/dist comes from the `web` stage above, so
# it always matches the sources rather than whatever was last built on the host.
# api/main.py mounts it at / so the React UI is served by the same process.
COPY --chown=app:app web/ ./web/
COPY --from=web --chown=app:app /web/dist ./web/dist
# bi/ carries the Power BI project (PBIR report + semantic model definitions) that
# tests/test_export_bi.py reads. Only the text definitions travel; bi/data/ (the
# regenerated CSVs and the TopoJSON) is excluded in .dockerignore, and the .pbix is
# gitignored, so this stays small.
COPY --chown=app:app bi/ ./bi/
# The four files committed under data/processed/ (3.9 MB): the two frozen tables,
# the July 2021 story and the notice carrying their licences. With them the image
# shows the project from Docker Hub alone, with nothing cloned and nothing
# mounted. A bind mount of data/ hides them and serves the host's copies instead.
COPY --chown=app:app data/processed/DATA_NOTICE.md data/processed/event_2021_web.json \
     data/processed/exposure.parquet data/processed/context.parquet ./data/processed/

USER app

EXPOSE 8501 8010

# The same image runs either Streamlit (default CMD, 8501) or the API with the
# React UI (uvicorn, 8010), so healthy means either one answers. Probing 8501
# only marked every API container unhealthy. Probed with python because the slim
# image ships no curl; urlopen raises on a refused connection or an error status,
# which makes python exit non-zero.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request as r; r.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=2)" \
     || python -c "import urllib.request as r; r.urlopen('http://127.0.0.1:8010/api/health', timeout=2)"

# Exec form, so Streamlit is PID 1 and gets SIGTERM directly from `docker stop`.
CMD ["python", "-m", "streamlit", "run", "app/streamlit_app.py", \
     "--server.port=8501", "--server.address=0.0.0.0"]


# --- The self-contained image -------------------------------------------------
# Same application, with the corpus and the rasters inside it. This is the one to
# build once the fetch has finished and to carry on a USB stick: it needs nothing
# from the venue network and nothing from the Windows machine.
#
# It is the LAST stage deliberately, so the default `docker build .` is the image
# that cannot fail for lack of data. It costs as much disk as data/ itself and a
# long first build; the alternative is a 1.6 GB image plus a folder someone has to
# remember to copy, and the folder is the half that gets forgotten.
#
# `*.part` files are excluded in .dockerignore, so a download that was still in
# flight at build time cannot be baked in as if it were a complete raster.
FROM app AS portable
COPY --chown=app:app data/ ./data/
