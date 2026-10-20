"""Scale-up build: mine the taxonomy from a LARGE billing segment + score all YTD.

  python scripts/build_full.py

Compared to the sample build, this:
  * predicts billing on a 400k-row mixed sample  -> ~200k billing rows
  * mines the taxonomy from ~80 fine clusters    -> a broader, time-proof taxonomy
  * retrains GLVQ + SOM 20x20 on that segment
  * embeds ALL 7-month rows and writes the FULL scoring file
    outputs/scoring_ytd_billing.xlsx (every billing line, top-3 cat/subcat + conf)

Every stage is cached; re-runs skip completed steps.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import clustering as C  # noqa: E402
from src import pipeline as P  # noqa: E402
from src import viz  # noqa: E402
from src import taxonomy_mining as TM  # noqa: E402
from src.billing_kernel import BillingKernel  # noqa: E402
from src.config import ARTIFACTS_DIR, CACHE_DIR, DATA_DIR, OUTPUTS_DIR, SEED  # noqa: E402
from src.embed import embed_cached  # noqa: E402

N_CANDIDATE = 400_000
K_CLUSTERS = 80
K_CATEGORIES = 14
MIN_LEAF = 250
GLVQ_EPOCHS = 30

SEG = ARTIFACTS_DIR / "billing_segment_full.parquet"
SEG_EMB = CACHE_DIR / "emb_billing_segment_full.npy"
CAND = DATA_DIR / "candidate_full.parquet"


def step(m: str) -> None:
    print(f"\n[{pd.Timestamp.now():%H:%M:%S}] {'='*70}\n[{pd.Timestamp.now():%H:%M:%S}] {m}\n")


def build_segment(df, kernel) -> tuple[pd.DataFrame, np.ndarray]:
    step(f"1 · build billing segment from {N_CANDIDATE:,} mixed rows")
    if SEG.exists() and SEG_EMB.exists():
        print("using cached full billing segment")
        return pd.read_parquet(SEG), np.load(SEG_EMB)
    if CAND.exists():
        cand = pd.read_parquet(CAND)
        print("using cached candidate sample")
    else:
        per = N_CANDIDATE // (df["month"].nunique() * 2)
        pieces = []
        for (m, h), g in df.groupby(["month", "billing_heuristic"]):
            pieces.append(g.sample(min(per, len(g)), random_state=SEED))
        cand = pd.concat(pieces)
        cand = cand.sample(min(N_CANDIDATE, len(cand)), random_state=SEED)
        cand.to_parquet(CAND)
        print("candidate sample built+cached")
    Xcand = embed_cached(cand["text_unit"], "candidate_full_400k")
    proba = kernel.predict(Xcand)
    mask = proba >= kernel.threshold
    seg = cand[mask].reset_index(drop=True)
    Xseg = Xcand[mask]
    seg.to_parquet(SEG)
    np.save(SEG_EMB, Xseg)
    print(f"billing segment: {len(seg):,} rows (predicted {int(mask.sum()):,})")
    return seg, Xseg


def cluster_and_mine(seg, X) -> tuple[np.ndarray, dict]:
    step(f"2 · clustering comparison + KMeans (k={K_CLUSTERS})")
    lbl_path = ARTIFACTS_DIR / "billing_cluster_labels_full.npy"
    cmp_path = ARTIFACTS_DIR / "clustering_comparison_full.json"
    if cmp_path.exists() and lbl_path.exists():
        print("using cached clustering (full)")
        labels = np.load(lbl_path)
    else:
        seed = json.loads((DATA_DIR / "seed_taxonomy_clean.json").read_text())
        seed_protos = np.load(ARTIFACTS_DIR / "subcat_seed_protos_clean.npy")
        table = C.evaluate(X, seg["month"].to_numpy(), seed_protos, k=K_CLUSTERS)
        print(table.round(4).to_string())
        best = C.choose_best(table)
        print("recommended algorithm:", best)
        table.to_json(ARTIFACTS_DIR / "clustering_comparison_full_table.json")
        _, labels, _ = C.fit_best(table, X, k=K_CLUSTERS)
        np.save(lbl_path, labels)
        json.dump({"best": best, "k": K_CLUSTERS}, open(cmp_path, "w"), indent=2)
        joblib_dump = __import__("joblib").dump
        joblib_dump(C.fit_best(table, X, k=K_CLUSTERS)[2],
                    ARTIFACTS_DIR / "billing_cluster_model_full.joblib")

    step("3 · mine the 2-level taxonomy at scale")
    mined_path = DATA_DIR / "taxonomy_mined_full.json"
    if mined_path.exists():
        mined = json.loads(mined_path.read_text())
        print("using cached mined taxonomy (full)")
    else:
        TM.MIN_LEAF = MIN_LEAF
        seg2 = seg.copy()
        seg2["cluster"] = labels
        mined = TM.mine(seg2, X, labels, k_categories=K_CATEGORIES)
        mined_path.write_text(json.dumps(mined, indent=2))
    n_sub = sum(len(c["subcategories"]) for c in mined["categories"])
    print(f"mined taxonomy: {len(mined['categories'])} categories, {n_sub} subcategories")
    return labels, mined


def train_and_viz(seg, X, labels, mined) -> None:
    step("4 · GLVQ + SOM + visualizations (full scale)")
    from src.embed import embed_subcategory_seeds
    from src.lvq import GLVQ
    from src.som import KohonenSOM

    glvq_path = ARTIFACTS_DIR / "glvq_full.joblib"
    keys_path = ARTIFACTS_DIR / "glvq_active_keys_full.json"
    if glvq_path.exists() and keys_path.exists():
        model = GLVQ.load(glvq_path)
        active = json.loads(keys_path.read_text())
        print("using cached GLVQ (full)")
    else:
        cluster2key = {sub["cluster"]: f"{cat['name']} :: {sub['name']}"
                       for cat in mined["categories"] for sub in cat["subcategories"]}
        sample_labels = [cluster2key.get(int(l), P.MISC_KEY) for l in labels]
        keys, seed_protos, _, _ = P.prepare_taxonomy_full()
        label_idx = {k: i for i, k in enumerate(keys)}
        model, report = P.train_lvq(X, sample_labels, keys, seed_protos,
                                    label_idx, epochs=GLVQ_EPOCHS)
        print(f"GLVQ report: {report}")
        active = json.loads((ARTIFACTS_DIR / "glvq_active_keys.json").read_text())
        glvq_path.write_bytes((ARTIFACTS_DIR / "glvq.joblib").read_bytes())
        keys_path.write_text(json.dumps(active, indent=2))

    som_path = ARTIFACTS_DIR / "som_full.joblib"
    if som_path.exists():
        som = KohonenSOM.load(som_path)
        print("using cached SOM (full)")
    else:
        som = KohonenSOM(grid=20, dim=X.shape[1], epochs=20, seed=SEED)
        som.fit(X, verbose=False)
        som.save(som_path)

    # visualizations at full scale
    cluster2key = {sub["cluster"]: f"{cat['name']} :: {sub['name']}"
                   for cat in mined["categories"] for sub in cat["subcategories"]}
    leaf_keys = np.array([cluster2key.get(int(l), P.MISC_KEY) for l in labels])
    cell_df = viz.som_cell_analysis(som, X, seg["text_unit"].tolist(),
                                    labels=leaf_keys, keys=active["active_keys"])
    viz.write_som_cells(cell_df, OUTPUTS_DIR / "som_cells_full.tsv")
    viz.som_cells_plot(som, som.accumulate_density(X), cell_df,
                       OUTPUTS_DIR / "som_cells_full.png")
    viz.som_3d(som, som.accumulate_density(X), OUTPUTS_DIR / "som_3d_full.png")
    hier = viz.som_hierarchy(cell_df, mined)
    vols = hier.groupby(["category", "subcategory"])["count"].sum().reset_index()
    viz.treemap(vols.rename(columns={"count": "volume"}),
                OUTPUTS_DIR / "treemap_full.png")
    viz.taxonomy_tree(mined, OUTPUTS_DIR / "taxonomy_tree_full.png")
    print("full-scale visualizations written")
    return model, active


def score_full(df, kernel, model, active) -> None:
    step("5 · score EVERY billing line of the 7-month YTD data")
    out = OUTPUTS_DIR / "scoring_ytd_billing.xlsx"
    if out.exists():
        print(f"using cached full scoring: {out}")
        return
    from scripts.score_ytd import score_full as _score
    _score(df, kernel, model, active["active_keys"], out=out)


def main() -> None:
    t0 = time.time()
    df = P.load_ml_dataset()
    df = P.add_heuristic_label(df)
    kernel = BillingKernel.load(ARTIFACTS_DIR / "billing_kernel.joblib")
    seg, X = build_segment(df, kernel)
    labels, mined = cluster_and_mine(seg, X)
    model, active = train_and_viz(seg, X, labels, mined)
    score_full(df, kernel, model, active)
    print(f"\nSCALE-UP DONE in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()