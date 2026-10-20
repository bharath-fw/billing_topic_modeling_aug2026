"""Run the full v2 pipeline at a Level-of-Service (LoS) sample scale.

Stage-by-stage execution with caching; prints diagnostics at each step so the
sample run can be reviewed before scaling up.

Run:  python scripts/build_los.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import pipeline as P  # noqa: E402
from src.config import ARTIFACTS_DIR, CACHE_DIR, OUTPUTS_DIR, SEED  # noqa: E402

N_KERNEL_SAMPLE = 40_000      # balanced sample for the billing kernel
N_CANDIDATE_SAMPLE = 120_000  # mixed rows we predict billing on for the segment
K_RANGE = (12, 60)            # silhouette sweep range for clusters


def main() -> None:
    t_start = time.time()
    print("=" * 90)
    print("STAGE 1 · load 7-month ML dataset")
    df = P.load_ml_dataset()
    df = P.add_heuristic_label(df)
    print(f"  rows (non-empty intent): {len(df):,}")
    print(df["billing_heuristic"].value_counts().to_string())

    print("=" * 90)
    print(f"STAGE 2 · train billing kernel (sample={N_KERNEL_SAMPLE})")
    kernel = P.train_billing_kernel(df, sample=N_KERNEL_SAMPLE,
                                    cache_key="los_kernel_40k")

    print("=" * 90)
    print(f"STAGE 3 · build billing segment (predict on {N_CANDIDATE_SAMPLE:,} mixed rows)")
    rng = np.random.RandomState(SEED)
    # stratify by month + heuristic to guarantee a healthy billing pool
    per_group = N_CANDIDATE_SAMPLE // (df["month"].nunique() * 2)
    pieces = []
    for (m, h), g in df.groupby(["month", "billing_heuristic"]):
        pieces.append(g.sample(min(per_group, len(g)), random_state=SEED))
    cand = pd.concat(pieces)
    cand = cand.sample(min(N_CANDIDATE_SAMPLE, len(cand)), random_state=SEED).reset_index(drop=True)
    proba = P.predict_billing(kernel, cand["text_unit"], "los_billing_pred_120k")
    cand["billing_prob"] = proba
    cand["billing_pred"] = (proba >= kernel.threshold).astype(int)
    print(f"  predicted billing: {int(cand['billing_pred'].sum()):,} of {len(cand):,}")
    print("  by month:")
    print(cand.groupby(["month", "billing_pred"]).size().unstack(fill_value=0).to_string())

    billing = cand[cand["billing_pred"] == 1].copy().reset_index(drop=True)
    print(f"billing segment: {len(billing):,} rows")

    print("=" * 90)
    print(f"STAGE 4 · cluster billing embeddings (silhouette sweep {K_RANGE})")
    Xb = np.load(CACHE_DIR / "emb_los_billing_pred_120k.npy")
    Xb = Xb[cand["billing_pred"].to_numpy() == 1]
    month_arr = billing["month"].to_numpy()
    cluster = P.cluster_billing(Xb, month_arr, k_range=K_RANGE, seed=SEED)
    print(f"  best_k = {cluster['best_k']}")
    print(f"  silhouette curve: { {k: round(s, 3) for k, s in cluster['curves'].items()} }")
    print("  per-month silhouette at best_k:")
    for m, s in cluster["month_silhouette"].items():
        print(f"    {m}: {s:.3f}" if s == s else f"    {m}: n/a")
    joblib_dump = __import__("joblib")
    joblib_dump.dump(cluster["model"], ARTIFACTS_DIR / "kmeans.joblib")
    np.save(ARTIFACTS_DIR / "cluster_labels_los.npy", cluster["labels"])

    print("=" * 90)
    print("STAGE 5 · map clusters -> taxonomy subcategories")
    subcat_keys, seed_protos, taxonomy, label_idx = P.prepare_taxonomy()
    mapping_res = P.map_clusters_to_subcats(cluster["model"].cluster_centers_,
                                            seed_protos, subcat_keys)
    mapping = mapping_res["mapping"]
    misc_count = sum(1 for v in mapping.values() if v == P.MISC_KEY)
    print(f"  {len(mapping)} clusters -> {len(set(mapping.values()))} subcategories "
          f"({misc_count} mapped to {P.MISC_KEY})")
    for c, key in sorted(mapping.items()):
        sim = float(mapping_res["sim"][c].max())
        print(f"    cluster {c:>2}: {key:<60} sim={sim:.3f}")
    P.save_subcategory_artifacts(subcat_keys, seed_protos, taxonomy, label_idx)

    sample_labels = P.cluster_label_to_subcat(cluster["labels"], mapping)
    billing["subcat_label"] = sample_labels
    print(billing["subcat_label"].value_counts().head(15).to_string())

    print("=" * 90)
    print("STAGE 6 · train GLVQ (90/10) — refines seed prototypes")
    model, report = P.train_lvq(Xb, sample_labels, subcat_keys, seed_protos,
                                label_idx, epochs=15)
    print(f"  {report}")

    print("=" * 90)
    print("STAGE 7 · Kohonen SOM density map")
    som = P.train_som(Xb, grid=28, epochs=20)
    dens = som.accumulate_density(Xb)
    print(f"  density map: {dens.sum():,} calls over {(dens > 0).sum()} cells "
          f"(peak {dens.max():,}/cell)")

    print("=" * 90)
    print("STAGE 8 · top-3 scoring for the billing segment (LoS sample)")
    active_keys = P.load_active_keys()
    score_df = P.score_topk(model, Xb, active_keys, k=3)
    out_path = P.write_scoring_xlsx(score_df, billing, kernel, OUTPUTS_DIR / "scoring_LoS_sample.xlsx")
    print(out_path)

    # distribution of top-1 categories
    cats = score_df["category_1"].value_counts()
    print("\nTop-1 category distribution (LoS sample):")
    print((cats / len(score_df) * 100).round(2).head(15).to_string())

    print("=" * 90)
    print(f"DONE in {(time.time() - t_start) / 60:.1f} min")


if __name__ == "__main__":
    main()