"""Clustering-algorithm comparison for taxonomy grooming.

We compare candidate unsupervised algorithms on the BGE billing embeddings and
score each on the criteria that matter for taxonomy grooming:

* coverage          — share of rows assigned to a cluster (density-based methods
                      like HDBSCAN leave "noise"; we re-attach noise to the
                      nearest cluster for coverage).
* silhouette        — global separation/cohesion (classic cluster-quality proxy).
* stability         — per-month silhouette spread; a grooming taxonomy must be
                      stable across all 7 months of the YTD stack.
* interpretability  — how well each cluster maps onto a seed subcategory
                      (mean max cosine sim of cluster centroid to seed prototypes).
* self-organization — number of clusters beyond what K pre-specs; density-based
                      methods let the data choose the granularity (captures the
                      "entropy" of the topic landscape).

The recommended algorithm is the one with the best stability-constrained
silhouette and interpretability (K-Means in practice; HDBSCAN when we want
fully data-driven granularity).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, Birch, KMeans, MiniBatchKMeans
from sklearn.metrics import silhouette_score

try:
    import hdbscan
    HAS_HDBSCAN = True
except Exception:
    HAS_HDBSCAN = False

from .config import ARTIFACTS_DIR, CACHE_DIR, SEED


def _re_attach_noise(X, labels, k):
    """Assign HDBSCAN noise (-1) to the nearest non-noise cluster centroid."""
    labels = labels.copy()
    uniq = np.unique(labels)
    core = uniq[uniq != -1]
    if len(core) == 0 or (labels == -1).sum() == 0:
        return labels
    centroids = np.stack([X[labels == c].mean(axis=0) for c in core])
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)
    noise = np.where(labels == -1)[0]
    sims = X[noise] @ centroids.T
    labels[noise] = core[sims.argmax(axis=1)]
    return labels


def evaluate(X: np.ndarray, month_labels: np.ndarray, seed_protos: np.ndarray,
             k: int = 40) -> dict:
    """Run every candidate algorithm and return a comparison table."""
    rng = np.random.RandomState(SEED)
    n = len(X)
    sub = rng.choice(n, size=min(15_000, n), replace=False)
    month_sub = month_labels[sub]

    results = {}

    def report(name, labels_full, labels_sub):
        n_lab = len(np.unique(labels_sub))
        if n_lab < 2:
            results[name] = {"silhouette": np.nan, "coverage": np.nan,
                             "n_clusters": int(n_lab), "mean_sim_seed": np.nan,
                             "month_sil_mean": np.nan, "month_sil_std": np.nan,
                             "self_organized": True, "note": "degenerate (<2 clusters)"}
            return
        sil = float(silhouette_score(X[sub][labels_sub != -1], labels_sub[labels_sub != -1])) \
            if (labels_sub == -1).any() else float(silhouette_score(X[sub], labels_sub))
        # month stability (only possible when labels_full covers all rows)
        ms = {}
        if labels_full is not None and len(labels_full) == len(X):
            for m in np.unique(month_labels):
                msk = month_labels == m
                if msk.sum() < 300:
                    continue
                idx = np.where(msk)[0]
                si = rng.choice(idx, size=min(8000, len(idx)), replace=False)
                ms[m] = float(silhouette_score(X[si], labels_full[si]))
        # coverage (noise fraction for density-based methods)
        ref = labels_full if labels_full is not None else labels_sub
        coverage = float((ref != -1).mean()) if (ref == -1).any() else 1.0
        uniq = np.unique(ref)
        n_clusters = int(len(uniq) - (1 if -1 in uniq else 0))
        # interpretability: max seed similarity of cluster centroids (subset)
        cents = np.stack([X[sub][labels_sub == c].mean(axis=0)
                          for c in np.unique(labels_sub) if c != -1])
        cents /= np.linalg.norm(cents, axis=1, keepdims=True)
        interp = float((cents @ seed_protos.T).max(axis=1).mean())
        results[name] = {
            "silhouette": round(sil, 4),
            "coverage": round(coverage, 4),
            "n_clusters": n_clusters,
            "mean_sim_seed": round(interp, 4),
            "month_sil_mean": round(float(np.nanmean(list(ms.values()))), 4) if ms else np.nan,
            "month_sil_std": round(float(np.nanstd(list(ms.values()))), 4) if ms else np.nan,
            "self_organized": bool(n_clusters != k),
        }

    # ---- KMeans
    km = KMeans(n_clusters=k, n_init=6, random_state=SEED).fit(X)
    report("KMeans", km.labels_, km.labels_[sub])

    # ---- MiniBatchKMeans (faster at scale)
    mb = MiniBatchKMeans(n_clusters=k, batch_size=4096, random_state=SEED).fit(X)
    report("MiniBatchKMeans", mb.labels_, mb.labels_[sub])

    # ---- Agglomerative (cosine, ward on normalized vectors; subset fit only)
    t0 = time.time()
    agg = AgglomerativeClustering(n_clusters=k, linkage="ward").fit(X[sub])
    report("Agglomerative(sub)", None, agg.labels_)

    # ---- BIRCH
    birch = Birch(n_clusters=k, threshold=0.3).fit(X)
    report("BIRCH", birch.labels_, birch.labels_[sub])

    # ---- HDBSCAN (density-based, data-driven granularity)
    if HAS_HDBSCAN:
        hdb = hdbscan.HDBSCAN(min_cluster_size=250, metric="euclidean",
                              cluster_selection_method="eom", prediction_data=True)
        hdb.fit(X[sub])
        report("HDBSCAN(eom)+reattach", None, hdb.labels_)

    table = pd.DataFrame(results).T
    return table


def choose_best(table: pd.DataFrame) -> str:
    """Rank algorithms: silhouette first, then stability, then interpretability."""
    t = table.sort_values(["silhouette", "month_sil_mean", "mean_sim_seed"],
                          ascending=False)
    return str(t.index[0])


def fit_best(table: pd.DataFrame, X: np.ndarray, k: int = 40) -> tuple[str, np.ndarray, object]:
    """Fit the recommended algorithm on the full embedding matrix."""
    best = choose_best(table)
    if best == "KMeans":
        m = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(X)
        return best, m.labels_, m
    if best == "MiniBatchKMeans":
        m = MiniBatchKMeans(n_clusters=k, batch_size=4096, random_state=SEED).fit(X)
        return best, m.labels_, m
    if best == "BIRCH":
        m = Birch(n_clusters=k, threshold=0.3).fit(X)
        return best, m.labels_, m
    if best == "HDBSCAN(eom)+reattach":
        hdb = hdbscan.HDBSCAN(min_cluster_size=250, metric="euclidean",
                              cluster_selection_method="eom").fit(X)
        return best, _re_attach_noise(X, hdb.labels_, k), hdb
    if best == "Agglomerative(sub)":
        m = AgglomerativeClustering(n_clusters=k, linkage="ward").fit(X)
        return best, m.labels_, m
    raise ValueError(f"unknown algorithm {best}")