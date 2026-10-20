# Docker — Brightspeed Call Analytics UI (CPU)

Runs the Streamlit UI on port **8501** with live bind-mounts to project `datasets/`, `code/pipeline`, `code/artifacts`, and `code/output`.

Default image uses **CPU PyTorch** (suitable for Google VM).

## Quick start (Google VM / CPU)

```bash
cd /path/to/billing_topic_modeling_aug2026

# Seed small September test extracts (4 x 50 rows)
mkdir -p datasets
cp testdata/*.xlsx datasets/

docker compose up --build -d
```

Open http://localhost:8501

Stop:

```bash
docker compose down
```

## Custom port

```bash
UI_PORT=8502 docker compose up --build -d
```

## Optional GPU (local NVIDIA host)

```bash
docker compose --profile gpu up --build -d ui-gpu
```

## What is mounted

| Host path | Container | Purpose |
|-----------|-----------|---------|
| `datasets/` | `/app/datasets` | Monthly / test Excel files |
| `code/pipeline/` | `/app/code/pipeline` | Ingest / narrow / coverage / autotag |
| `code/artifacts/` | `/app/code/artifacts` | Taxonomy JSON + centroids |
| `code/output/` | `/app/code/output` | Prototypes + tagged Excel outputs |
| `brightspeed_ui/ui_runs/` | `/app/brightspeed_ui/ui_runs` | Per-run logs and results |
| Docker volume `hf_models` | `/models` | Cached Hugging Face / BGE model |

The UI resolves the project via `PROJECT_ROOT=/app`.

## Notes

- First tagging run downloads `BAAI/bge-large-en-v1.5` into the `hf_models` volume (can take several minutes on CPU).
- Prefer the `testdata/` extracts on a VM; full monthly dumps are multi‑hundred MB each.
- Ensure the VM has enough RAM for embedding/tagging (several GB recommended even for small batches).
- If you see `PermissionError` on `ui_runs` / `datasets` / `code/output`, fix host ownership then restart:

```bash
sudo chown -R 1000:1000 brightspeed_ui/ui_runs code/output datasets
docker compose restart ui
```

  (Or rebuild after pulling — the image runs as root so bind mounts stay writable.)
