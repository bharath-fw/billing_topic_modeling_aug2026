"""End-to-end orchestration for the v2 pipeline.

Every stage is implemented here as a small function so both the build script and
the explanatory notebooks can share the exact same code paths.

Stage flow
----------
1. load ML dataset (7 months, one row per call)
2. heuristic billing label from Primary Call Reason
3. BillingKernel (embeddings) -> probability billing / non-billing  [saved]
4. billing-only segment (rows whose billing prob >= threshold)
5. K-Means clustering on BGE embeddings + silhouette sweep (stable across months)
6. cluster -> taxonomy subcategory mapping (nearest seed prototype; < threshold -> Misc/Other)
7. GLVQ prototype model (refines seed prototypes)                   [saved]
8. Kohonen SOM density map                                          [saved]
9. top-3 category/subcategory scoring for the billing segment       [xlsx]
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from .billing_kernel import BillingKernel
from .config import (
    ARTIFACTS_DIR, BILLING_CATEGORIES, CACHE_DIR, DATA_DIR, EMBED_DIM, EMBED_MODEL_NAME,
    LVQ_ALPHA0, LVQ_EPOCHS, ML_DATASET, OUTPUTS_DIR, SEED, SOM_EPOCHS, SOM_GRID,
    TAXONOMY_JSON,
)
from .embed import embed_cached, embed_subcategory_seeds, embed_texts
from .lvq import GLVQ
from .som import KohonenSOM

# taxonomy fallback subcategory for clusters with no confident mapping
MISC_CATEGORY = "Other Category"
MISC_SUBCATEGORY = "Misc/Other"
MISC_KEY = f"{MISC_CATEGORY} :: {MISC_SUBCATEGORY}"

CLUSTER_MAP_THRESHOLD = 0.30      # min cosine sim between cluster centroid & seed


# ---------------------------------------------------------------- stage 1
def load_ml_dataset(path: Path = ML_DATASET) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df = df[df["call_intent"].str.strip() != ""].reset_index(drop=True)
    return df


def add_heuristic_label(df: pd.DataFrame) -> pd.DataFrame:
    """billing_heuristic = Primary Call Reason in the billing/payment set."""
    df = df.copy()
    df["billing_heuristic"] = df["category"].isin(BILLING_CATEGORIES).astype(int)
    return df


# ---------------------------------------------------------------- stage 3
def train_billing_kernel(df: pd.DataFrame, sample: int = 40_000,
                         cache_key: str = "billing_kernel_train") -> BillingKernel:
    t0 = time.time()
    kernel = BillingKernel.train(df["text_unit"], df["billing_heuristic"],
                                 sample_balance=sample, cache_key=cache_key)
    print(f"billing kernel metrics: {kernel.metrics}")
    kernel.save(ARTIFACTS_DIR / "billing_kernel.joblib")
    print(f"billing kernel saved ({time.time()-t0:.0f}s)")
    return kernel


def predict_billing(kernel: BillingKernel, texts: pd.Series,
                    cache_key: str) -> np.ndarray:
    X = embed_cached(texts, cache_key)
    return kernel.predict(X)


# ---------------------------------------------------------------- stage 5
def cluster_billing(X: np.ndarray, month_labels: np.ndarray, k_range: tuple[int, int] = (12, 60),
                    stride: int = 4, seed: int = SEED) -> dict:
    """K-Means with silhouette sweep + month-stability check.

    Returns a dict with the fitted model, labels, silhouette curve and a
    per-month optimal-k stability report.
    """
    ks = list(range(k_range[0], k_range[1] + 1, stride))
    sub_idx = np.random.RandomState(seed).choice(
        len(X), size=min(20_000, len(X)), replace=False)
    curves = {}
    for k in ks:
        km = KMeans(n_clusters=k, n_init=4, random_state=seed).fit(X[sub_idx])
        curves[k] = float(silhouette_score(X[sub_idx], km.labels_))
    best_k = max(curves, key=curves.get)
    km = KMeans(n_clusters=best_k, n_init=10, random_state=seed).fit(X)
    labels = km.labels_

    # per-month stability: silhouette of best_k evaluated on each month's subset
    month_k = {}
    uniq = np.unique(month_labels)
    for m in uniq:
        msk = month_labels == m
        if msk.sum() < 300:
            month_k[m] = np.nan
            continue
        sub = np.random.RandomState(seed).choice(
            np.where(msk)[0], size=min(8000, int(msk.sum())), replace=False)
        km_m = KMeans(n_clusters=best_k, n_init=4, random_state=seed).fit(X[sub])
        month_k[m] = float(silhouette_score(X[sub], km_m.labels_))

    sizes = np.bincount(labels, minlength=best_k)
    return {
        "model": km, "labels": labels, "best_k": int(best_k), "curves": curves,
        "month_silhouette": month_k,
        "cluster_sizes": {int(i): int(c) for i, c in enumerate(sizes)},
    }


# ---------------------------------------------------------------- stage 6
def map_clusters_to_subcats(cluster_centroids: np.ndarray,
                            seed_protos: np.ndarray,
                            subcat_keys: list[str],
                            threshold: float = CLUSTER_MAP_THRESHOLD) -> dict:
    """Map each cluster to the taxonomy subcategory it best matches.

    A cluster maps to the seed prototype with the highest cosine similarity; if
    that similarity is below `threshold` the cluster is assigned to Misc/Other.
    """
    sim = cluster_centroids @ seed_protos.T       # (n_clusters, n_subcats)
    best_idx = sim.argmax(axis=1)
    best_sim = sim.max(axis=1)
    mapping = {}
    for c in range(len(cluster_centroids)):
        if best_sim[c] >= threshold:
            mapping[int(c)] = subcat_keys[int(best_idx[c])]
        else:
            mapping[int(c)] = MISC_KEY
    return {"mapping": mapping, "sim": sim}


def cluster_label_to_subcat(labels: np.ndarray, mapping: dict) -> list[str]:
    return [mapping.get(int(l), MISC_KEY) for l in labels]


# ---------------------------------------------------------------- stage 7
def train_lvq(X: np.ndarray, sample_labels: np.ndarray, subcat_keys: list[str],
              seed_protos: np.ndarray, label_idx: dict[str, int],
              epochs: int = LVQ_EPOCHS, alpha0: float = LVQ_ALPHA0,
              test_frac: float = 0.1, min_samples: int = 60) -> tuple[GLVQ, dict]:
    """Train GLVQ on a 90/10 split using only the ACTIVE subcategories.

    Only subcategories that the data actually supports (>= min_samples mapped
    rows) get prototypes; the remaining taxonomy seeds are excluded so they
    cannot steal billing samples during scoring.  Returns (model, report).
    """
    from collections import Counter
    from sklearn.model_selection import train_test_split

    counts = Counter(sample_labels)
    # fold tiny subcategories into Misc/Other
    folded = [k for k, c in counts.items() if c < min_samples and k != MISC_KEY]
    eff_labels = [MISC_KEY if k in folded else k for k in sample_labels]
    eff_counts = Counter(eff_labels)
    active_keys = sorted(eff_counts.keys())
    if MISC_KEY not in active_keys:
        active_keys.append(MISC_KEY)

    label_to_idx = {k: i for i, k in enumerate(active_keys)}
    y = np.array([label_to_idx[k] for k in eff_labels], dtype=int)

    # seed prototypes: one per active key (taxonomy seed, or data mean for Misc)
    misc_seed = X.mean(axis=0)
    protos = []
    for k in active_keys:
        if k in label_idx:
            protos.append(seed_protos[label_idx[k]])
        else:
            protos.append(misc_seed)
    protos = np.stack(protos)
    protos = protos / np.linalg.norm(protos, axis=1, keepdims=True)
    prototype_labels = np.array([label_to_idx[k] for k in active_keys], dtype=int)

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=test_frac,
                                          random_state=SEED, stratify=y)
    model = GLVQ(n_prototypes=len(active_keys), dim=X.shape[1], epochs=epochs,
                 alpha0=alpha0, seed=SEED)
    model.fit(Xtr, ytr, protos, prototype_labels, verbose=True)

    pred = model.predict(Xte)
    report = {
        "test_acc": float((pred == yte).mean()),
        "n_active_subcats": len(active_keys),
        "folded_subcats": folded,
    }
    protos = model.prototypes_
    inter = protos @ protos.T
    np.fill_diagonal(inter, np.nan)
    report["mean_inter_proto_sim"] = float(np.nanmean(inter))
    report["test_n"] = int(len(yte))
    # save model + active key mapping for scoring
    model.save(ARTIFACTS_DIR / "glvq.joblib")
    (ARTIFACTS_DIR / "glvq_active_keys.json").write_text(
        json.dumps({"active_keys": active_keys, "label_to_idx": label_to_idx,
                    "misc_key": MISC_KEY}, indent=2))
    return model, report


# ---------------------------------------------------------------- stage 8
def train_som(X: np.ndarray, grid: int = SOM_GRID, epochs: int = SOM_EPOCHS) -> KohonenSOM:
    som = KohonenSOM(grid=grid, dim=X.shape[1], epochs=epochs, seed=SEED)
    som.fit(X, verbose=True)
    som.save(ARTIFACTS_DIR / "som.joblib")
    return som


# ---------------------------------------------------------------- stage 9
def score_topk(model: GLVQ, X: np.ndarray, keys: list[str],
               k: int = 3) -> pd.DataFrame:
    """Top-k category/subcategory + confidence for every row.

    keys must be the ACTIVE prototype keys (one per model prototype).
    """
    top_idx, top_sim, top_prob = model.predict_proba_topk(X, k)
    rows = []
    for i in range(len(X)):
        rec = {}
        for r in range(k):
            key = keys[top_idx[i, r]]
            cat, sub = key.split(" :: ", 1)
            rec[f"category_{r+1}"] = cat
            rec[f"subcategory_{r+1}"] = sub
            rec[f"conf_{r+1}"] = round(float(top_prob[i, r]), 4)
        rows.append(rec)
    return pd.DataFrame(rows)


def load_active_keys() -> list[str]:
    return json.loads((ARTIFACTS_DIR / "glvq_active_keys.json").read_text())["active_keys"]


def write_scoring_xlsx(score_df: pd.DataFrame, billing_df: pd.DataFrame,
                       kernel: BillingKernel | None, path: Path) -> Path:
    """Write the final single scoring file (XLSX) for the billing segment."""
    out = pd.concat([billing_df.reset_index(drop=True), score_df.reset_index(drop=True)],
                    axis=1)
    out.insert(2, "billing_related", 1)
    cols = ["ytd_call_id", "call_intent", "billing_related", "call_date", "month",
            "ban", "network_type", "record_id", "category"]
    cols += [c for c in out.columns if c.startswith(("category_", "subcategory_", "conf_"))]
    out = out[[c for c in cols if c in out.columns]]
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        out.to_excel(xw, sheet_name="Billing_Scoring", index=False)
        if kernel is not None:
            pd.DataFrame([kernel.metrics]).T.to_excel(xw, sheet_name="Model_Metrics")
    print(f"scoring file written: {path} ({len(out):,} rows)")
    return path


def save_subcategory_artifacts(subcat_keys: list[str], seed_protos: np.ndarray,
                               taxonomy: dict, label_idx: dict[str, int]) -> None:
    payload = {
        "subcat_keys": subcat_keys,
        "label_idx": label_idx,
        "misc_key": MISC_KEY,
        "misc_category": MISC_CATEGORY,
        "misc_subcategory": MISC_SUBCATEGORY,
        "n_subcats": len(subcat_keys),
        "embed_model": EMBED_MODEL_NAME,
        "taxonomy": taxonomy,
    }
    np.save(ARTIFACTS_DIR / "subcat_seed_protos.npy", seed_protos)
    (ARTIFACTS_DIR / "subcat_artifacts.json").write_text(
        json.dumps(payload, indent=2))
    print(f"subcategory artifacts saved ({len(subcat_keys)} prototypes)")


def load_subcategory_artifacts() -> dict:
    return json.loads((ARTIFACTS_DIR / "subcat_artifacts.json").read_text())


def prepare_taxonomy_full() -> tuple[list[str], np.ndarray, dict, dict]:
    """Load the FULL-scale mined taxonomy + embed its subcategory descriptions."""
    mined = json.loads((DATA_DIR / "taxonomy_mined_full.json").read_text())
    flat = {f"{c['name']} :: {s['name']}": f"{s['name']} - {', '.join(s['keywords'])}"
            for c in mined["categories"] for s in c["subcategories"]}
    keys = list(flat.keys())
    P, _ = embed_subcategory_seeds(flat)
    label_idx = {k: i for i, k in enumerate(keys)}
    return keys, P, mined, label_idx


def prepare_taxonomy() -> tuple[list[str], np.ndarray, dict, dict]:
    """Load the MINED taxonomy + embed its subcategory descriptions.

    Returns (keys, seed_protos, mined, label_idx):
      keys      : mined leaf keys "Category :: Subcategory"
      seed_protos : embedded prototype seeds (leaf descriptions, data-derived)
      mined     : the mined taxonomy dict
      label_idx : {key: int}
    """
    mined = json.loads((DATA_DIR / "taxonomy_mined.json").read_text())
    flat = {f"{c['name']} :: {s['name']}": f"{s['name']} - {', '.join(s['keywords'])}"
            for c in mined["categories"] for s in c["subcategories"]}
    keys = list(flat.keys())
    P, _ = embed_subcategory_seeds(flat)
    label_idx = {k: i for i, k in enumerate(keys)}
    return keys, P, mined, label_idx