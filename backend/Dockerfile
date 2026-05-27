# syntax=docker/dockerfile:1
#
# API server image (FastAPI + uvicorn).
# Deliberately does NOT include Playwright/chromium — server.py never imports
# it; only the crawler does. See Dockerfile.crawler for that.
# Python 3.10 to match the dev venv (pinned wheels: spacy/blis/thinc/presidio).

############################  builder  ############################
FROM python:3.10-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Toolchain in case any pinned wheel needs to compile (cffi/jq/blis fallbacks).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# requirements-prod.txt = requirements.txt minus dev tools (black/flake8/mypy/
# isort/pytest) and playwright. The en_core_web_lg spacy model is pulled here
# via its wheel URL — no separate `spacy download` step needed.
COPY requirements-prod.txt .
RUN pip install --upgrade pip \
    && pip install --prefix=/install -r requirements-prod.txt

############################  runtime  ############################
FROM python:3.10-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# ffmpeg  -> pydub (voice features in speech_service.py)
# libgomp1 -> OpenMP runtime for blis/numpy/thinc
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 10001 appuser

# Installed Python packages (incl. spacy model) from the builder stage.
COPY --from=builder /install /usr/local

# App code (build context is backend/; .dockerignore strips venv/tests/etc).
COPY . /app

# uploads/ and logs/ are bind-mounted at runtime; create + own them so the
# non-root user can write even before the volume mounts.
RUN mkdir -p /app/uploads /app/logs && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# run_server.py carries the uvicorn tuning (large-upload keep-alive, h11 cap
# disabled) — prefer it over a bare `uvicorn server:app`.
CMD ["python", "run_server.py"]
