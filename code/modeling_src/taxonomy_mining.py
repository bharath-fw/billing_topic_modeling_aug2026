"""Data-driven taxonomy mining — NOT seed replication.

The manually-compiled seed files are reference material ONLY.  This module mines a
naturally-organizing 2-level billing taxonomy directly from the BGE embeddings:

* clusters are discovered on the embedding vectors (K-Means, silhouette-tuned);
* every leaf (subcategory) is labelled from ITS OWN member texts — top TF-IDF
  keywords + representative sentences — never from the seed vocabulary;
* the two-level hierarchy is self-organized: coarse categories are formed by
  agglomerative grouping of the cluster centroids (embedding similarity), so the
  taxonomy reflects the actual topic landscape of the YTD billing segment.

Output ``data/taxonomy_mined.json``:
    {
      "categories": [{"name": "...", "subcategories": [ {
            "name": "...", "keywords": [...], "rep": "...", "cluster": n, "count": m,
            "share": 0.04 } ] }],
      "meta": {...}
    }
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from .config import DATA_DIR, SEED

OUT_JSON = DATA_DIR / "taxonomy_mined.json"

CATEGORY_K = 12          # coarse top-level categories (self-organized)
MIN_LEAF = 120           # clusters smaller than this fold into the parent Misc
N_KEYWORDS = 5           # keywords emitted per leaf
N_REP = 1                # representative sentences per leaf


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# leading filler that repeats across nearly every call-intent sentence
_PREFIX = re.compile(
    r"^(customer|agent|the customer|the agent|caller|account)\s+"
    r"(?:contacted|said|states?|claims?|called|asks?|requested|wants?|needed|was|"
    r"received|inquired|inquire|believe|wanted|advised|reported|is|has|had|"
    r"experienced|noticed|was being|was experiencing|reached out)\s*",
    re.IGNORECASE,
)


def _leaf_name(keywords: list[str], rep: str) -> str:
    """Human-readable leaf label from the representative sentence.

    Prefers a clean noun-phrase pulled from the representative text; falls back
    to a deduplicated keyword join when the text is unhelpful.
    """
    t = _clean(rep or "")
    t = re.sub(r"[,.!?;]$", "", t)
    t = _PREFIX.sub("", t)
    # drop trailing filler clause
    t = re.split(r"[,;] and|\bhowever\b|\bafter the agent\b|\band the agent\b", t)[0]
    t = t.split(". ")[0].strip()
    t = t.split("!")[0].strip()
    words = t.split()
    if 2 <= len(words) <= 10:
        return t.title()[:64]
    if len(words) > 10:
        return " ".join(words[:6]).title().rstrip(" ,")[:64] + "…"
    # fall back: dedup keywords, skip the most generic terms
    seen, out = set(), []
    for k in keywords:
        if k not in seen and k.split()[0] not in seen and k not in {
                "customer", "service", "payment"}:
            seen.add(k)
            seen.add(k.split()[0])
            out.append(k)
        if len(out) >= 3:
            break
    return " ".join(out).title()[:64] or "Unlabeled Topic"


def _category_name(keywords_union: list[str]) -> str:
    """Category name from the most frequent distinct unigrams across its leaves."""
    from collections import Counter
    skip = {"customer", "agent", "service", "payment", "billing", "account"}
    cnt = Counter(k.split()[0] for k in keywords_union)
    words = [w for w, _ in cnt.most_common() if w not in skip][:3]
    return " ".join(words).title()[:48] or "Billing Topic"


def mine(billing_df: pd.DataFrame, X: np.ndarray, cluster_labels: np.ndarray,
         k_categories: int = CATEGORY_K, cluster_key: str = "cluster") -> dict:
    """Mine the self-organized 2-level taxonomy from the embeddings.

    Parameters
    ----------
    billing_df : billing segment with ``text_unit``
    X : BGE embeddings (aligned to billing_df rows)
    cluster_labels : fine-grained cluster id per row
    """
    texts = billing_df["text_unit"].tolist()
    tfv = TfidfVectorizer(ngram_range=(1, 2), max_features=15_000,
                          stop_words="english", min_df=5)
    Tf = tfv.fit_transform(texts)
    feat = np.array(tfv.get_feature_names_out())

    # ---- fine clusters -> leaf evidence
    uniq = np.unique(cluster_labels)
    centroids = np.stack([X[cluster_labels == c].mean(axis=0) for c in uniq])
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)

    leaves = []
    for c in uniq:
        mask = cluster_labels == c
        n = int(mask.sum())
        if n < MIN_LEAF:
            continue
        means = Tf[mask].mean(axis=0).A1
        kw = [feat[j] for j in np.argsort(means)[::-1][:N_KEYWORDS]]
        cx = centroids[np.where(uniq == c)[0][0]]
        dist = np.linalg.norm(X[mask] - cx, axis=1)
        rep_idx = np.where(mask)[0][int(np.argmin(dist))]
        rep = _clean(str(texts[rep_idx]))[:220]
        leaves.append({
            "cluster": int(c), "count": n,
            "keywords": kw, "rep": rep,
            "name": _leaf_name(kw, rep),
        })
    if not leaves:
        raise ValueError("no leaves mined")

    leaf_idx = np.array([l["cluster"] for l in leaves])

    # ---- coarse categories: agglomerative grouping of leaf centroids in the
    # embedding space (cosine-like via ward on normalised vectors)
    leaf_cents = np.stack([centroids[np.where(uniq == c)[0][0]] for c in leaf_idx])
    kc = min(k_categories, len(leaves))
    agg = AgglomerativeClustering(n_clusters=kc, linkage="ward").fit(leaf_cents)
    cat_ids = agg.labels_

    # ---- assemble the hierarchy
    categories = []
    for g in range(kc):
        members = [leaves[i] for i in np.where(cat_ids == g)[0]]
        members.sort(key=lambda l: -l["count"])
        all_kw = []
        for m in members:
            for k in m["keywords"]:
                if k not in all_kw:
                    all_kw.append(k)
        cat = {
            "name": _category_name(all_kw),
            "count": int(sum(m["count"] for m in members)),
            "share": round(float(sum(m["count"] for m in members) / len(billing_df)), 4),
            "subcategories": members,
        }
        categories.append(cat)
    categories.sort(key=lambda c: -c["count"])

    # ---- enforce unique names so leaf keys never collide
    used_cat = {}
    for cat in categories:
        base = cat["name"]
        if base in used_cat:
            used_cat[base] += 1
            cat["name"] = f"{base} {used_cat[base]}"
        else:
            used_cat[base] = 1
        used_sub = {}
        for sub in cat["subcategories"]:
            if sub["name"] in used_sub:
                used_sub[sub["name"]] += 1
                sub["name"] = f"{sub['name']} ({used_sub[sub['name']]})"
            else:
                used_sub[sub["name"]] = 1

    mined = {
        "categories": categories,
        "meta": {
            "n_rows": int(len(billing_df)),
            "n_categories": len(categories),
            "n_subcategories": len(leaves),
            "k_categories": kc,
            "cluster_alg": "KMeans",
            "embed_model": "BAAI/bge-large-en-v1.5",
        },
    }
    OUT_JSON.write_text(json.dumps(mined, indent=2))
    print(f"mined taxonomy: {len(categories)} categories, {len(leaves)} subcategories "
          f"from {len(billing_df):,} billing rows")
    return mined


def mined_to_flat(mined: dict) -> dict:
    """Convert mined taxonomy to {leaf_key: {"category","subcategory","keywords","rep"}}."""
    flat = {}
    for cat in mined["categories"]:
        for sub in cat["subcategories"]:
            key = f"{cat['name']} :: {sub['name']}"
            flat[key] = {
                "category": cat["name"], "subcategory": sub["name"],
                "keywords": sub["keywords"], "rep": sub["rep"],
                "cluster": sub["cluster"], "count": sub["count"],
            }
    return flat


def leaf_key_for_cluster(mined: dict, cluster: int) -> str:
    for cat in mined["categories"]:
        for sub in cat["subcategories"]:
            if sub["cluster"] == cluster:
                return f"{cat['name']} :: {sub['name']}"
    return "Other Category :: Misc/Other"