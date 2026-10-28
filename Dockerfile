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
# **Two stages, because the data is 6.4 GiB** (measured 2026-10-23). `app` holds the code only and
# expects `data/` to be bind-mounted - that is the day-to-day image, rebuilt in
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
FROM ${BASE_IMAGE} AS app

# MPLCONFIGDIR is set because matplotlib builds a font cache on first import and
# warns loudly when its config directory is not writable, which it is not for a
# non-root user whose home directory the image never visits.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_HEADLESS=true \
    MPLCONFIGDIR=/tmp/matplotlib

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
# 6.4 GiB into this stage too. Being explicit also means a new file at the repo
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
# web/ carries the Vite sources and, when it was built on the host beforehand,
# web/dist - which api/main.py mounts at / so the React UI is served by the same
# process. The image has no Node toolchain, so dist is never built here.
COPY --chown=app:app web/ ./web/

USER app

EXPOSE 8501 8010

# Streamlit's own liveness endpoint. Probed with python because the slim image
# ships no curl.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4).status == 200 else 1)"]

# Exec form, so Streamlit is PID 1 and gets SIGTERM directly from `docker stop`.
CMD ["python", "-m", "streamlit", "run", "app/streamlit_app.py", \
     "--server.port=8501", "--server.address=0.0.0.0"]


# --- The self-contained image -------------------------------------------------
# Same application, with the corpus and the rasters inside it. This is the one to
# build once the fetch has finished and to carry on a USB stick: it needs nothing
# from the venue network and nothing from the Windows machine.
#
# It is the LAST stage deliberately, so the default `docker build .` is the image
# that cannot fail for lack of data. It costs ~6.5 GiB and a long first build; the
# alternative is a 2 GiB image plus a folder someone has to remember to copy, and
# the folder is the half that gets forgotten.
#
# `*.part` files are excluded in .dockerignore, so a download that was still in
# flight at build time cannot be baked in as if it were a complete raster.
FROM app AS portable
COPY --chown=app:app data/ ./data/
