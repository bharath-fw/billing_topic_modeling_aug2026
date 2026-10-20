"""Taxonomy grooming.

The manually-compiled seed taxonomy (``billing_categories.txt`` +
``billing_subcategories_deeper.txt``) is a *seed*, not the final vocabulary.  This
module turns it into a comprehensive, deduplicated, data-verified 2-level
hierarchy (Category :: Subcategory):

1. ``reconcile_seed``   — remove redundant duplicates (embedding-similarity merge).
2. ``groom``            — walk the discovered billing clusters: clusters that match
                          a seed subcategory confirm it; clusters with no confident
                          seed match become NEW subcategories (named from their
                          TF-IDF keywords + representative text).  This grows the
                          taxonomy so it covers every billing issue present in the
                          YTD segment, not just what the seed happened to list.

Output ``data/taxonomy_groomed.json``:
    {
      "categories": ["Bill Dispute", ...],
      "taxonomy": {"Bill Dispute": ["Late fee dispute", "Incorrect billing ...", ...]},
      "subcategory_vocab": {"Bill Dispute :: Late fee dispute": "Bill Dispute - Late fee dispute", ...},
      "provenance": {"Bill Dispute :: Late fee dispute": "seed", "New Cat :: New sub": "discovered"},
      "meta": {...}
    }
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ARTIFACTS_DIR, DATA_DIR, SEED
from .embed import embed_cached, embed_subcategory_seeds, embed_texts
from .pipeline import MISC_KEY

SEED_JSON = DATA_DIR / "taxonomy.json"          # parsed seed (from scripts/taxonomy.py)
OUT_JSON = DATA_DIR / "taxonomy_groomed.json"

MERGE_SIM = 0.94          # seed subcats above this cosine sim are duplicates
CLUSTER_SEED_SIM = 0.32   # min cosine sim to confirm a seed subcategory for a cluster
CLUSTER_CAT_SIM = 0.22    # min sim to place a discovered subcat into an existing category
MIN_CLUSTER = 150         # clusters below this size are folded into Misc/Other


def _canonical_key(cat: str, sub: str) -> str:
    return f"{cat} :: {sub}"


def _clean(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip(" -.,")


def reconcile_seed() -> dict:
    """Load seed taxonomy, merge near-duplicate subcategories via embedding sim.

    Returns {"taxonomy": {cat: [subs]}, "subcategory_vocab": {key: desc},
             "label_idx": {key: int}} with duplicates folded onto the first key.
    """
    data = json.loads(SEED_JSON.read_text())
    vocab = data["subcategory_vocab"]              # key -> "Cat - Sub"
    keys = list(vocab.keys())
    descs = [vocab[k] for k in keys]
    P = embed_cached(pd.Series(descs), "seed_clean_emb")
    sim = P @ P.T
    drop = set()
    keep_key = {}
    for i in range(len(keys)):
        if keys[i] in drop:
            continue
        for j in range(i + 1, len(keys)):
            if sim[i, j] >= MERGE_SIM:
                drop.add(keys[j])
                keep_key[keys[j]] = keys[i]
    clean_keys = [k for k in keys if k not in drop]
    clean_vocab = {k: vocab[k] for k in clean_keys}
    # rebuild nested taxonomy from clean keys
    tax = {}
    for k in clean_keys:
        cat, sub = k.split(" :: ", 1)
        tax.setdefault(cat, []).append(sub)
    label_idx = {k: i for i, k in enumerate(clean_keys)}
    print(f"reconciled seed: {len(keys)} -> {len(clean_keys)} subcategories "
          f"({len(drop)} duplicates merged)")
    return {"taxonomy": tax, "subcategory_vocab": clean_vocab,
            "label_idx": label_idx, "duplicates": keep_key}


def _cluster_evidence(texts: list[str], tfidf_cache: tuple | None = None):
    from sklearn.feature_extraction.text import TfidfVectorizer

    tfv = TfidfVectorizer(ngram_range=(1, 2), max_features=12_000,
                          stop_words="english", min_df=5)
    Tf = tfv.fit_transform(texts)
    feat = np.array(tfv.get_feature_names_out())
    return Tf, feat


def _top_keywords(Tf, feat, mask, n=6) -> list[str]:
    means = Tf[mask].mean(axis=0).A1
    return [feat[j] for j in np.argsort(means)[::-1][:n]]


def groom(billing_df: pd.DataFrame, X: np.ndarray, cluster_labels: np.ndarray,
          seed: dict, cluster_key: str = "cluster") -> dict:
    """Build the groomed taxonomy from the discovered clusters.

    Parameters
    ----------
    billing_df : billing segment with a ``text_unit`` column
    X : BGE embeddings of the billing segment (aligned to billing_df rows)
    cluster_labels : cluster id per row (from the chosen clustering)
    seed : output of ``reconcile_seed()``

    Returns
    -------
    dict with the groomed taxonomy + provenance + per-cluster assignment.
    """
    seed_keys = list(seed["subcategory_vocab"].keys())
    seed_protos = np.load(ARTIFACTS_DIR / "subcat_seed_protos_clean.npy")
    seed_cat_of = {k: k.split(" :: ", 1)[0] for k in seed_keys}
    # category prototypes = mean of their subcat prototypes
    cat_names = sorted({seed_cat_of[k] for k in seed_keys})
    cat_protos = np.stack([
        seed_protos[[seed["label_idx"][k] for k in seed_keys
                     if seed_cat_of[k] == c]].mean(axis=0)
        for c in cat_names
    ])
    cat_protos /= np.linalg.norm(cat_protos, axis=1, keepdims=True)

    Tf, feat = _cluster_evidence(billing_df["text_unit"].tolist())
    centers = np.stack([X[cluster_labels == c].mean(axis=0)
                        for c in np.unique(cluster_labels)])
    centers /= np.linalg.norm(centers, axis=1, keepdims=True)

    sim2seed = centers @ seed_protos.T
    sim2cat = centers @ cat_protos.T

    taxonomy: dict[str, list[str]] = {}
    provenance: dict[str, str] = {}
    assignments = {}
    new_counter = {}
    for c in np.unique(cluster_labels):
        n = int((cluster_labels == c).sum())
        if n < MIN_CLUSTER:
            assignments[int(c)] = MISC_KEY
            continue
        ks = int(np.argmax(sim2seed[c]))
        cs = int(np.argmax(sim2cat[c]))
        if sim2seed[c, ks] >= CLUSTER_SEED_SIM:
            key = seed_keys[ks]
            cat, sub = key.split(" :: ", 1)
            assignments[int(c)] = key
            provenance.setdefault(key, "seed")
        elif sim2cat[c, cs] >= CLUSTER_CAT_SIM:
            cat = cat_names[cs]
            sub = _name_discovered(_top_keywords(Tf, feat, cluster_labels == c))
            key = _canonical_key(cat, sub)
            if key in new_counter:
                new_counter[key] += 1
                key = _canonical_key(cat, f"{sub} ({new_counter[key]})")
            else:
                new_counter[key] = 1
            assignments[int(c)] = key
            provenance.setdefault(key, "discovered")
        else:
            cat = "Other Category"
            sub = _name_discovered(_top_keywords(Tf, feat, cluster_labels == c))
            key = _canonical_key(cat, sub)
            if key in new_counter:
                new_counter[key] += 1
                key = _canonical_key(cat, f"{sub} ({new_counter[key]})")
            else:
                new_counter[key] = 1
            assignments[int(c)] = key
            provenance.setdefault(key, "discovered")

    # rebuild taxonomy dict
    for key in assignments.values():
        if key == MISC_KEY:
            continue
        cat, sub = key.split(" :: ", 1)
        taxonomy.setdefault(cat, []).append(sub)
    # ensure Misc/Other always exists
    taxonomy.setdefault(MISC_KEY.split(" :: ", 1)[0], []).append(
        MISC_KEY.split(" :: ", 1)[1])
    provenance[MISC_KEY] = "fallback"

    # rebuild vocabulary from the groomed hierarchy
    vocab = {}
    for cat, subs in taxonomy.items():
        for sub in subs:
            key = _canonical_key(cat, sub)
            vocab[key] = f"{cat} - {sub}"

    groomed = {
        "categories": sorted(taxonomy.keys()),
        "taxonomy": taxonomy,
        "subcategory_vocab": vocab,
        "provenance": provenance,
        "assignments": {str(k): v for k, v in assignments.items()},
        "n_clusters": int(len(np.unique(cluster_labels))),
        "meta": {"seed_merge_sim": MERGE_SIM, "cluster_seed_sim": CLUSTER_SEED_SIM,
                 "min_cluster": MIN_CLUSTER, "seed_subcats": len(seed_keys),
                 "groomed_subcats": len(vocab),
                 "discovered": sum(1 for v in provenance.values() if v == "discovered")},
    }
    OUT_JSON.write_text(json.dumps(groomed, indent=2))
    print(f"groomed taxonomy: {len(taxonomy)} categories, {len(vocab)} subcategories "
          f"({groomed['meta']['discovered']} discovered from data)")
    return groomed


def _name_discovered(keywords: list[str]) -> str:
    name = " ".join(keywords[:3])
    return _clean(name.title()[:80]) or "Unlabeled Topic"


def embed_clean_seeds(seed: dict) -> np.ndarray:
    """Embed the reconciled seed vocab and cache the prototype matrix."""
    keys = list(seed["subcategory_vocab"].keys())
    P, _ = embed_subcategory_seeds(seed["subcategory_vocab"])
    np.save(ARTIFACTS_DIR / "subcat_seed_protos_clean.npy", P)
    return P


def save_clean_seed(seed: dict) -> None:
    (DATA_DIR / "seed_taxonomy_clean.json").write_text(json.dumps(
        {"taxonomy": seed["taxonomy"], "subcategory_vocab": seed["subcategory_vocab"],
         "label_idx": seed["label_idx"], "duplicates": seed["duplicates"]}, indent=2))