"""Local, GPU-accelerated AI category tagging of Brightspeed billing calls.

This replaces the offline ChatGPT-Excel tagging step: instead of a human classifying
each call with an LLM prompt, we classify every call locally by embedding its
structured narrative with BAAI/bge-large-en-v1.5 and matching against the 104 curated
billing-taxonomy leaf prototypes (downloaded/cached from the coverage-validation run).

For each call we emit up to three tags (``ai_tag_1/2/3``) plus their category and
subcategory.  Rank-2/rank-3 are only filled for a genuinely *independent* second/third
ask: a leaf whose macro category differs from the already-selected one(s) and whose
cosine similarity clears the threshold.  Falls back to OTHER_MISC_OTHER_BILLING when
nothing clears threshold (a modest, expected fallback share).

Output: ``code/output/billing_tagged_full.parquet`` (ready for report.py) and a
per-category summary CSV.

Pass ``--limit N`` to tag only the first N rows (useful for quick sanity tests).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import coverage as C

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "code" / "data"
OUT = ROOT / "code" / "output"
FALLBACK_TAG = "OTHER_MISC_OTHER_BILLING"
FALLBACK_CAT = "Other Category"
FALLBACK_SUB = "Misc or Other billing"
MAX_CHARS = 700
THRESHOLD = 0.30


def assign_tags(sims: np.ndarray, leaf_df: pd.DataFrame, threshold: float = THRESHOLD,
                max_ranks: int = 3) -> pd.DataFrame:
    """Assign up to 3 tags per row from cosine sims (narrative x leaf).

    Rank 1 = argmax sim.  Each subsequent rank = best remaining leaf whose
    *category differs* from every category already chosen AND sim >= threshold.
    """
    n = sims.shape[0]
    tags = leaf_df["canonical_tag"].to_numpy()
    cats = leaf_df["category"].to_numpy()
    subs = leaf_df["subcategory"].to_numpy()
    m = len(tags)

    cols = {}
    for r in range(1, max_ranks + 1):
        cols[f"ai_tag_{r}"] = np.array([FALLBACK_TAG] * n, dtype=object)
        cols[f"ai_category_{r}"] = np.array([FALLBACK_CAT] * n, dtype=object)
        cols[f"ai_subcategory_{r}"] = np.array([FALLBACK_SUB] * n, dtype=object)

    # order leaves by sim per row once; iterate down ranks
    order = np.argsort(-sims, axis=1, kind="stable")     # n x m
    best_sim = np.take_along_axis(sims, order[:, :1], axis=1)[:, 0]

    selected_cat = np.empty((n, max_ranks), dtype=object)  # categories used per row
    selected_cat[:, :] = None

    for r in range(max_ranks):
        idx = order[:, r].copy()                          # candidate leaf per row
        s = sims[np.arange(n), idx]
        ok = s >= threshold
        if r > 0:
            # reject if the candidate category was already selected
            for rr in range(r):
                already = selected_cat[:, rr]
                same_cat = np.array([cats[idx[i]] == already[i] if already[i] is not None else False
                                     for i in range(n)], dtype=bool)
                ok = ok & ~same_cat
        row_msk = np.arange(n)[ok]
        if len(row_msk) == 0:
            break
        cols[f"ai_tag_{r+1}"][row_msk] = tags[idx[row_msk]]
        cols[f"ai_category_{r+1}"][row_msk] = cats[idx[row_msk]]
        cols[f"ai_subcategory_{r+1}"][row_msk] = subs[idx[row_msk]]
        selected_cat[row_msk, r] = cats[idx[row_msk]]

    out = pd.DataFrame(cols)
    out.insert(0, "_sim1", np.round(best_sim, 4))
    return out


def run(limit: int | None = None, device: str | None = None,
        out_file: Path | None = None) -> Path:
    out_file = out_file or (OUT / "billing_tagged_full.parquet")
    OUT.mkdir(parents=True, exist_ok=True)

    narrow = pd.read_parquet(DATA / "billing_narrow.parquet")
    if limit:
        narrow = narrow.head(limit).copy()
    print(f"tagging {len(narrow):,} billing/payments calls")

    narr = C.build_narratives(narrow, max_chars=MAX_CHARS)
    print("embedding narratives ...")
    narr_vecs = C.embed(narr["narrative"].tolist(), device=device)

    leaf_df = pd.read_csv(OUT / "coverage_leaf_order.csv")
    protos = np.load(OUT / "coverage_leaf_protos.npy")
    print("scoring against", len(leaf_df), "leaf prototypes ...")
    sims = C.score_coverage(narr_vecs, protos)

    tagged = assign_tags(sims, leaf_df)
    out = pd.concat([narrow.reset_index(drop=True), tagged], axis=1)

    # add the aggregated category column report.py expects
    out["_category"] = out["ai_category_1"].fillna(FALLBACK_CAT)
    out["_tag"] = out["ai_tag_1"].fillna(FALLBACK_TAG)

    out.to_parquet(out_file, index=False)
    print("wrote", out_file)

    # summary
    summ = out.groupby(["Call_Month", "ai_category_1"]).size().reset_index(name="calls")
    summ.to_csv(OUT / "billing_tagged_summary.csv", index=False)
    share = out["ai_category_1"].value_counts(normalize=True).mul(100).round(2)
    print("--- top categories by share ---")
    print(share.head(12).to_string())
    fb = 100 * (out["ai_tag_1"] == FALLBACK_TAG).mean()
    print(f"fallback (OTHER_MISC) share: {fb:.2f}%")
    return out_file


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--device", default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    path = run(limit=args.limit, device=args.device, out_file=args.out)
    print("DONE ->", path)
