"""Shared configuration + paths for the v2 topic-modeling pipeline."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
YTD_DATA_DIR = ROOT / "ytd_data"
ARTIFACTS_DIR = ROOT / "artifacts"
OUTPUTS_DIR = ROOT / "outputs"
NOTEBOOKS_DIR = ROOT / "notebooks"
SCRIPTS_DIR = ROOT / "scripts"
CACHE_DIR = ARTIFACTS_DIR / "cache"

ML_DATASET = DATA_DIR / "ytd_ml_dataset.parquet"
TAXONOMY_JSON = DATA_DIR / "taxonomy.json"

EMBED_MODEL_NAME = "BAAI/bge-large-en-v1.5"
EMBED_DIM = 1024

# Heuristic billing signal: Primary Call Reason values treated as billing-related.
BILLING_CATEGORIES = {"Billing", "Payments"}

# Seed / random state
SEED = 42

# LVQ / SOM defaults
LVQ_EPOCHS = 20
LVQ_ALPHA0 = 0.3
SOM_GRID = 20          # 20x20 Kohonen map
SOM_EPOCHS = 25

for d in (ARTIFACTS_DIR, OUTPUTS_DIR, CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)

__all__ = [
    "ROOT", "DATA_DIR", "YTD_DATA_DIR", "ARTIFACTS_DIR", "OUTPUTS_DIR",
    "NOTEBOOKS_DIR", "SCRIPTS_DIR", "CACHE_DIR",
    "ML_DATASET", "TAXONOMY_JSON",
    "EMBED_MODEL_NAME", "EMBED_DIM",
    "BILLING_CATEGORIES", "SEED",
    "LVQ_EPOCHS", "LVQ_ALPHA0", "SOM_GRID", "SOM_EPOCHS",
]