"""Taxonomy coverage validation for Brightspeed billing calls.

Purpose
-------
Check whether the existing 104-leaf billing taxonomy (``artifacts/taxonomy.json``
+ ``artifacts/curated_centroids_10_each.csv``) is *representatively good enough* to
cover the call narratives in the reprocessed billing/payments data.

Method
------
For each sampled call we build a single structured narrative:

    "Customer Intent Tag | Problem Identified Tag | Reason | Summary"

(boundaries marked with a ``<|sep|>`` token so the four parts stay distinct in the
vector).  Every narrative is embedded whole with BAAI/bge-large-en-v1.5.

Taxonomy side: each of the 104 canonical leaves is represented by up to 10 curated
centroid texts (from ``curated_centroids_10_each.csv``); the mean of a leaf's centroid
embeddings is that leaf's prototype.  A call narrative is "covered" when its nearest
leaf-prototype cosine similarity exceeds a threshold (default 0.30, matching the
existing pipeline's ``CLUSTER_MAP_THRESHOLD``).

Outputs
-------
* Per-leaf and per-category coverage tables (CSV).
* A "coverage report" JSON with overall / category / fallback metrics plus a random
  sample of the most-uncovered narratives for human review.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import pandas as pd

from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "code" / "artifacts"
DATA = ROOT / "code" / "data"
OUT = ROOT / "code" / "output"

EMBED_MODEL = "BAAI/bge-large-en-v1.5"
COVERAGE_THRESHOLD = 0.30
SEP = " <|sep|> "
RANDOM_SEED = 42

_model: SentenceTransformer | None = None
_model_device: str | None = None


def get_embedder(device: str | None = None) -> SentenceTransformer:
    """Load BGE once per process and keep it warm for all encode calls."""
    global _model, _model_device
    want = device or "cpu"
    if _model is None:
        print(f"loading embedding model {EMBED_MODEL} on {want} ...", flush=True)
        _model = SentenceTransformer(EMBED_MODEL, device=want)
        _model_device = want
        # Warm-up so the first real batch is not dominated by lazy init.
        _model.encode(["warmup"], batch_size=1, normalize_embeddings=True,
                      convert_to_numpy=True, show_progress_bar=False)
        print("embedding model ready", flush=True)
    elif want != _model_device:
        print(f"moving embedding model {_model_device} -> {want} ...", flush=True)
        _model = _model.to(want)
        _model_device = want
    return _model


def embed(
    texts: list[str],
    batch_size: int | None = None,
    device: str | None = None,
    show_progress_bar: bool | None = None,
) -> np.ndarray:
    if not texts:
        return np.zeros((0, 1024), dtype=np.float32)
    model = get_embedder(device)
    # CPU VMs: moderate batches; GPU can take larger ones.
    if batch_size is None:
        batch_size = 32 if (device or _model_device or "cpu") == "cpu" else 128
    if show_progress_bar is None:
        show_progress_bar = len(texts) >= 32
    return model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=show_progress_bar,
    ).astype(np.float32)


# ------------------------------------------------------------------ taxonomy
def load_taxonomy_leaves() -> pd.DataFrame:
    """Return one row per canonical leaf with category, subcategory, definition."""
    tax = json.loads((ARTIFACTS / "taxonomy.json").read_text())
    rows = []
    for cat in tax["categories"]:
        for sub in cat["subcategories"]:
            rows.append({
                "canonical_tag": sub["canonical_tag"],
                "category": cat["name"],
                "subcategory": sub["name"],
                "definition": sub.get("definition", ""),
                "keywords": " ".join(sub.get("keywords", [])),
            })
    return pd.DataFrame(rows)


def load_centroid_texts() -> pd.DataFrame:
    return pd.read_csv(ARTIFACTS / "curated_centroids_10_each.csv")


def build_leaf_prototype_texts() -> pd.DataFrame:
    """Combine curated centroid texts + taxonomy definition into per-leaf texts."""
    leaves = load_taxonomy_leaves()
    cents = load_centroid_texts()
    rows = []
    for _, leaf in leaves.iterrows():
        tag = leaf["canonical_tag"]
        leaf_cents = cents[cents["canonical_tag"] == tag]["centroid_text"].tolist()
        texts = leaf_cents[:10]
        if not texts:
            texts = [f"{leaf['subcategory']} - {leaf['keywords']}".strip()]
        rows.append({
            "canonical_tag": tag,
            "category": leaf["category"],
            "subcategory": leaf["subcategory"],
            "definition": leaf["definition"],
            "prototype_texts": texts,
        })
    return pd.DataFrame(rows)


def build_leaf_prototypes(prot_texts: pd.DataFrame, device=None) -> pd.DataFrame:
    """Embed all leaf prototype texts in one batched pass, then mean-pool per leaf."""
    all_texts: list[str] = []
    spans: list[tuple[int, int]] = []
    meta: list[dict] = []
    for _, leaf in prot_texts.iterrows():
        texts = list(leaf["prototype_texts"]) or [""]
        start = len(all_texts)
        all_texts.extend(texts)
        spans.append((start, len(all_texts)))
        meta.append({
            "canonical_tag": leaf["canonical_tag"],
            "category": leaf["category"],
            "subcategory": leaf["subcategory"],
        })

    print(
        f"embedding {len(all_texts):,} prototype texts for {len(meta)} leaves "
        f"in one batched encode ...",
        flush=True,
    )
    vecs = embed(all_texts, device=device, show_progress_bar=True)

    out = []
    for (start, end), info in zip(spans, meta):
        proto = vecs[start:end].mean(axis=0)
        norm = float(np.linalg.norm(proto)) or 1.0
        proto = proto / norm
        out.append({**info, "prototype": proto.astype(np.float32)})
    return pd.DataFrame(out)


# ------------------------------------------------------------------ narratives
def build_narratives(narrow: pd.DataFrame, max_chars: int = 1200) -> pd.DataFrame:
    """Build the structured call-narrative text for each row.

    A single narrative keeps the four structured parts distinct with a ``<|sep|>``
    token.  The long ``Summary`` paragraph is the bulk of the text; to keep
    embedding fast (bge-large has a 512-token context anyway) the whole narrative
    is truncated to ``max_chars`` so short-but-salient intents stay intact.
    """
    n = narrow.copy()
    n["narrative"] = (
        n["Customer Intent Tag"].fillna("")
        + SEP + n["Problem Identified Tag"].fillna("")
        + SEP + n["Reason"].fillna("")
        + SEP + n["Summary"].fillna("")
    )
    n["narrative"] = n["narrative"].str.replace(SEP + SEP, SEP, regex=False).str.strip()
    # truncate each narrative to a bounded length (prefer the structured head)
    n["narrative"] = n["narrative"].map(lambda s: s[:max_chars] if len(s) > max_chars else s)
    return n


def sample_data(narrow: pd.DataFrame, frac: float = 0.20,
                seed: int = RANDOM_SEED) -> pd.DataFrame:
    rng = random.Random(seed)
    return narrow.sample(frac=frac, random_state=seed).reset_index(drop=True)


# ------------------------------------------------------------------ coverage
def score_coverage(narr_vecs: np.ndarray, leaf_protos: np.ndarray) -> np.ndarray:
    """Cosine similarity of each narrative to each leaf prototype."""
    return narr_vecs @ leaf_protos.T          # narrative x leaf


def coverage_report(narrow_sample: pd.DataFrame, sims: np.ndarray,
                    leaf_df: pd.DataFrame, threshold: float = COVERAGE_THRESHOLD,
                    top_uncovered: int = 30) -> dict:
    n, m = sims.shape
    best_idx = np.argmax(sims, axis=1)
    best_sim = sims[np.arange(n), best_idx]
    best_tag = leaf_df.iloc[best_idx]["canonical_tag"].to_numpy()
    best_cat = leaf_df.iloc[best_idx]["category"].to_numpy()
    best_sub = leaf_df.iloc[best_idx]["subcategory"].to_numpy()

    covered = best_sim >= threshold
    n_covered = int(covered.sum())
    n_fallback = n - n_covered

    covered_s = pd.Series(covered)

    # per-category coverage
    cat_rows = []
    for cat in pd.unique(best_cat):
        grp_idx = np.where(best_cat == cat)[0]
        g = covered_s.iloc[grp_idx]
        cat_rows.append({"category": cat, "calls": len(g),
                         "covered": int(g.sum()),
                         "coverage_pct": round(100 * g.mean(), 2)})
    cat_df = pd.DataFrame(cat_rows).reset_index(drop=True)

    # per-leaf coverage
    leaf_rows = []
    for tag in leaf_df["canonical_tag"].unique():
        msk = best_tag == tag
        if msk.sum() == 0:
            continue
        g = covered_s[msk]
        leaf_rows.append({"canonical_tag": tag, "calls": int(msk.sum()),
                          "covered": int(g.sum()),
                          "coverage_pct": round(100 * g.mean(), 2)})
    leaf_df_count = pd.DataFrame(leaf_rows).reset_index(drop=True)

    # uncovered sample for human review (lowest sim, non-empty narrative)
    narrow = narrow_sample.copy()
    narrow["_sim"] = best_sim
    narrow["_tag"] = best_tag
    narrow["_cat"] = best_cat
    narrow["_covered"] = covered
    unc = narrow[~covered]
    unc = unc[unc["narrative"].str.len() > 5]
    review = unc.nsmallest(top_uncovered, "_sim")[
        ["record_id", "Call_Month", "narrative", "_sim", "_tag", "_cat"]].copy()
    review["_sim"] = review["_sim"].round(3)

    return {
        "n_samples": int(n),
        "n_covered": n_covered,
        "n_fallback": n_fallback,
        "coverage_pct": round(100 * n_covered / max(n, 1), 2),
        "fallback_pct": round(100 * n_fallback / max(n, 1), 2),
        "threshold": threshold,
        "mean_best_sim": round(float(best_sim.mean()), 4),
        "median_best_sim": round(float(np.median(best_sim)), 4),
        "category_coverage": cat_df.to_dict("records"),
        "leaf_coverage": leaf_df_count.sort_values("calls", ascending=False).to_dict("records"),
        "uncovered_review": review.to_dict("records"),
    }


def run(frac: float = 0.20, threshold: float = COVERAGE_THRESHOLD,
        device: str | None = None, max_chars: int = 1200,
        out_dir: Path | None = None) -> dict:
    out_dir = out_dir or OUT
    out_dir.mkdir(parents=True, exist_ok=True)

    narrow = pd.read_parquet(DATA / "billing_narrow.parquet")
    print(f"billing narrow: {len(narrow):,} rows")
    sample = sample_data(narrow, frac=frac)
    print(f"sampling {len(sample):,} rows ({frac:.0%})")

    narr = build_narratives(sample, max_chars=max_chars)
    print("embedding narratives ...")
    narr_vecs = embed(narr["narrative"].tolist(), device=device)
    np.save(out_dir / "coverage_narrative_embs.npy", narr_vecs)
    narr.to_parquet(out_dir / "coverage_sample.parquet", index=False)

    print("building taxonomy leaf prototypes ...")
    prot_texts = build_leaf_prototype_texts()
    leaf_df = build_leaf_prototypes(prot_texts, device=device)
    protos = np.stack(leaf_df["prototype"].to_numpy())
    np.save(out_dir / "coverage_leaf_protos.npy", protos)
    leaf_df.drop(columns="prototype").to_csv(out_dir / "coverage_leaf_order.csv", index=False)

    print("scoring coverage ...")
    sims = score_coverage(narr_vecs, protos)
    report = coverage_report(narr, sims, leaf_df.drop(columns="prototype"),
                             threshold=threshold)
    (out_dir / "coverage_report.json").write_text(json.dumps(report, indent=2))
    pd.DataFrame(report["category_coverage"]).to_csv(
        out_dir / "coverage_by_category.csv", index=False)
    pd.DataFrame(report["leaf_coverage"]).to_csv(
        out_dir / "coverage_by_leaf.csv", index=False)
    return report


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--frac", type=float, default=0.20)
    ap.add_argument("--threshold", type=float, default=COVERAGE_THRESHOLD)
    ap.add_argument("--device", default=None)
    ap.add_argument("--max-chars", type=int, default=1200)
    args = ap.parse_args()
    rep = run(frac=args.frac, threshold=args.threshold, device=args.device,
              max_chars=args.max_chars)
    print(json.dumps({k: v for k, v in rep.items()
                      if k not in {"category_coverage", "leaf_coverage",
                                   "uncovered_review"}}, indent=2))
