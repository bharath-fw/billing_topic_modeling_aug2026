# Brightspeed billing taxonomy UI + pipeline
# Build:  docker compose build
# Run:    docker compose up ui
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models \
    TRANSFORMERS_CACHE=/models \
    SENTENCE_TRANSFORMERS_HOME=/models \
    PROJECT_ROOT=/app \
    UI_RUNS_DIR=/app/brightspeed_ui/ui_runs \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-docker.txt /app/requirements-docker.txt

# TORCH_INDEX: CPU default; override at build for CUDA, e.g.
#   --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu124
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN pip install --upgrade pip \
    && pip install torch --index-url "${TORCH_INDEX}" \
    && pip install -r /app/requirements-docker.txt

# App code baked into the image; datasets/code are also bind-mounted at runtime
COPY brightspeed_ui /app/brightspeed_ui
COPY code/pipeline /app/code/pipeline
COPY code/artifacts /app/code/artifacts
COPY code/docker/requirements.txt /app/code/docker/requirements.txt

RUN mkdir -p /app/datasets /app/code/output /app/brightspeed_ui/ui_runs /models \
    && useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app /models

USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "brightspeed_ui/app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--browser.gatherUsageStats=false"]
