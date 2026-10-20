"""Shared embedding utilities.

Whole-string encoding with the BGE-large-en-v1.5 sentence transformer — no
sentence splitting, no chunking, no collation with labels: the entire short
call-intent string is embedded as one vector.

```python
vector = embedding_model.encode("Customer upset about delayed shipping refund")
```

Embeddings are L2-normalised so cosine similarity == dot product.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

from .config import CACHE_DIR, EMBED_MODEL_NAME

_cache_model: SentenceTransformer | None = None


def get_embedder(model_name: str = EMBED_MODEL_NAME, device: str | None = None):
    """Load (and cache) the sentence transformer once per process."""
    global _cache_model
    if _cache_model is None:
        _cache_model = SentenceTransformer(model_name, device=device or _default_device())
    return _cache_model


def _default_device() -> str:
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def embed_texts(texts: list[str], batch_size: int = 128, show_progress: bool = True) -> np.ndarray:
    """Embed a list of short strings (whole-string, normalised, float32)."""
    model = get_embedder()
    return model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=show_progress,
    ).astype(np.float32)


def embed_cached(texts: pd.Series | list[str], cache_key: str, batch_size: int = 128) -> np.ndarray:
    """Embed with a numpy cache on disk (keyed cache) so re-runs are instant."""
    path = CACHE_DIR / f"emb_{cache_key}.npy"
    if path.exists():
        return np.load(path)
    t0 = time.time()
    X = embed_texts(list(texts), batch_size=batch_size)
    np.save(path, X)
    print(f"embedded {len(X):,} -> {X.shape} ({time.time()-t0:.0f}s) cached at {path.name}")
    return X


def embed_subcategory_seeds(seeds: dict[str, str], batch_size: int = 64) -> tuple[np.ndarray, list[str]]:
    """Embed taxonomy subcategory seed descriptions -> prototype matrix.

    Returns (normalised prototype matrix, ordered key list).
    """
    keys = list(seeds.keys())
    descs = list(seeds.values())
    P = embed_texts(descs, batch_size=batch_size)
    return P, keys