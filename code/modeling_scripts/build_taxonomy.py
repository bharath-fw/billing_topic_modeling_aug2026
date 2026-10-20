"""Build the v2 billing taxonomy & topic model (with progress caching).

Every expensive stage is cached to disk so re-runs skip completed steps.

  python scripts/build_taxonomy.py            # sample build (fast iteration)
  python scripts/build_taxonomy.py --full     # full 7-month billing segment

Flow (all stages cacheable):
  load data -> heuristic label -> billing kernel -> billing segment
  -> reconcile seed -> cluster (compare algorithms) -> groom taxonomy
  -> GLVQ (90/10) -> SOM 20x20 -> cell hierarchy -> top-3 scoring -> XLSX
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import clustering as C  # noqa: E402
from src import pipeline as P  # noqa: E402
from src import viz  # noqa: E402
from src import taxonomy_mining as TM  # noqa: E402
from src.billing_kernel import BillingKernel  # noqa: E402
from src.config import ARTIFACTS_DIR, CACHE_DIR, DATA_DIR, OUTPUTS_DIR, SEED  # noqa: E402
from src.embed import embed_subcategory_seeds  # noqa: E402

N_KERNEL_SAMPLE = 40_000
N_CANDIDATE_SAMPLE = 120_000
K_SILHOUETTE_RANGE = (15, 60)
K_CLUSTERS = 40          # final cluster count for taxonomy grooming
CLUSTER_ALGO = "KMeans"  # recommended algorithm (see comparison table)


def now() -> str:
    return pd.Timestamp.now().strftime("%H:%M:%S")


def step(msg: str) -> None:
    print(f"\n[{now()}] {'='*70}\n[{now()}] {msg}\n[{now()}] {'='*70}")


# ------------------------------------------------------------ cached stages
def stage_load_data() -> pd.DataFrame:
    df = P.load_ml_dataset()
    df = P.add_heuristic_label(df)
    print(f"ML dataset: {len(df):,} rows")
    return df


def stage_billing_kernel(df: pd.DataFrame) -> BillingKernel:
    kb = ARTIFACTS_DIR / "billing_kernel.joblib"
    if kb.exists():
        print("using cached billing kernel")
        return BillingKernel.load(kb)
    kernel = P.train_billing_kernel(df, sample=N_KERNEL_SAMPLE,
                                    cache_key="kernel_40k")
    return kernel


def stage_billing_segment(df: pd.DataFrame, kernel: BillingKernel) -> tuple[pd.DataFrame, np.ndarray]:
    seg_path = ARTIFACTS_DIR / "billing_segment_sample.parquet"
    emb_path = CACHE_DIR / "emb_billing_segment_sample.npy"
    if seg_path.exists() and emb_path.exists():
        seg = pd.read_parquet(seg_path)
        X = np.load(emb_path)
        print(f"using cached billing segment: {len(seg):,} rows")
        return seg, X
    # candidate sample (cached)
    cand_path = DATA_DIR / "candidate_sample.parquet"
    if cand_path.exists():
        cand = pd.read_parquet(cand_path)
        print(f"using cached candidate sample: {len(cand):,} rows")
    else:
        per_group = N_CANDIDATE_SAMPLE // (df["month"].nunique() * 2)
        pieces = []
        for (m, h), g in df.groupby(["month", "billing_heuristic"]):
            pieces.append(g.sample(min(per_group, len(g)), random_state=SEED))
        cand = pd.concat(pieces)
        cand = cand.sample(min(N_CANDIDATE_SAMPLE, len(cand)), random_state=SEED)
        cand.to_parquet(cand_path)
        print(f"candidate sample built+cached: {len(cand):,} rows")
    Xcand = _embed(cand["text_unit"], "candidate_120k")
    proba = kernel.predict(Xcand)
    cand["billing_prob"] = proba
    cand["billing_pred"] = (proba >= kernel.threshold).astype(int)
    seg = cand[cand["billing_pred"] == 1].reset_index(drop=True)
    Xseg = Xcand[cand["billing_pred"].to_numpy() == 1]
    seg.to_parquet(seg_path)
    np.save(emb_path, Xseg)
    print(f"billing segment built+cached: {len(seg):,} rows "
          f"(predicted {int(cand['billing_pred'].sum()):,} of {len(cand):,})")
    return seg, Xseg


def _embed(texts, key: str) -> np.ndarray:
    from src.embed import embed_cached
    return embed_cached(pd.Series(texts), key)


def stage_seed_reconcile() -> dict:
    path = DATA_DIR / "seed_taxonomy_clean.json"
    if path.exists():
        d = json.loads(path.read_text())
        print(f"using cached reconciled seed ({len(d['subcategory_vocab'])} subcats)")
        return d
    seed = TG.reconcile_seed()
    TG.embed_clean_seeds(seed)
    TG.save_clean_seed(seed)
    return seed


def stage_clustering(seg: pd.DataFrame, X: np.ndarray) -> tuple[pd.DataFrame, dict]:
    """Run the algorithm comparison, cache it, and return (table, report)."""
    report_path = ARTIFACTS_DIR / "clustering_comparison.json"
    if report_path.exists():
        table = pd.read_json(ARTIFACTS_DIR / "clustering_comparison_table.json")
        print("using cached clustering comparison")
        return table, json.loads(report_path.read_text())
    seed = json.loads((DATA_DIR / "seed_taxonomy_clean.json").read_text())
    seed_protos = np.load(ARTIFACTS_DIR / "subcat_seed_protos_clean.npy")
    table = C.evaluate(X, seg["month"].to_numpy(), seed_protos, k=K_CLUSTERS)
    print("\nClustering-algorithm comparison for taxonomy grooming:")
    print(table.round(4).to_string())
    best = C.choose_best(table)
    table.to_json(ARTIFACTS_DIR / "clustering_comparison_table.json")
    report = {"best": best, "k": K_CLUSTERS,
              "table": table.round(4).to_dict()}
    json.dump(report, open(report_path, "w"), indent=2, default=str)
    print(f"recommended algorithm for taxonomy grooming: {best}")
    return table, report


def stage_fit_clusters(X: np.ndarray, table: pd.DataFrame) -> np.ndarray:
    lbl_path = ARTIFACTS_DIR / "billing_cluster_labels.npy"
    if lbl_path.exists() and (ARTIFACTS_DIR / "billing_cluster_model.joblib").exists():
        print("using cached cluster labels")
        return np.load(lbl_path)
    best, labels, model = C.fit_best(table, X, k=K_CLUSTERS)
    np.save(lbl_path, labels)
    joblib.dump(model, ARTIFACTS_DIR / "billing_cluster_model.joblib")
    print(f"fitted {best}: {len(np.unique(labels))} clusters")
    return labels


def stage_mine(seg: pd.DataFrame, X: np.ndarray, labels: np.ndarray) -> dict:
    path = DATA_DIR / "taxonomy_mined.json"
    if path.exists():
        print("using cached mined taxonomy")
        return json.loads(path.read_text())
    seg = seg.copy()
    seg["cluster"] = labels
    mined = TM.mine(seg, X, labels)
    return mined


def stage_glvq(X: np.ndarray, labels: np.ndarray, mined: dict) -> tuple:
    from src.lvq import GLVQ
    glvq_path = ARTIFACTS_DIR / "glvq.joblib"
    keys_path = ARTIFACTS_DIR / "glvq_active_keys.json"
    if glvq_path.exists() and keys_path.exists():
        print("using cached GLVQ")
        model = GLVQ.load(glvq_path)
        return model, json.loads(keys_path.read_text())
    # map each cluster -> mined leaf key (fallback: Misc/Other)
    cluster2key = {sub["cluster"]: f"{cat['name']} :: {sub['name']}"
                   for cat in mined["categories"] for sub in cat["subcategories"]}
    sample_labels = [cluster2key.get(int(l), P.MISC_KEY) for l in labels]
    keys, seed_protos, _, _ = P.prepare_taxonomy()
    label_idx = {k: i for i, k in enumerate(keys)}
    model, report = P.train_lvq(X, sample_labels, keys, seed_protos, label_idx,
                                epochs=20)
    print(f"GLVQ report: {report}")
    return model, json.loads((ARTIFACTS_DIR / "glvq_active_keys.json").read_text())


def stage_som(X: np.ndarray) -> "KohonenSOM":
    from src.som import KohonenSOM
    som_path = ARTIFACTS_DIR / "som20.joblib"
    if som_path.exists():
        print("using cached SOM")
        return KohonenSOM.load(som_path)
    som = KohonenSOM(grid=20, dim=X.shape[1], epochs=20, seed=SEED)
    som.fit(X, verbose=False)
    som.save(som_path)
    print("SOM 20x20 trained+cached")
    return som


def stage_score(seg: pd.DataFrame, X: np.ndarray, model, active_keys: list[str],
                kernel: BillingKernel, out: Path) -> Path:
    if out.exists():
        print(f"using cached scoring file: {out}")
        return out
    score_df = P.score_topk(model, X, active_keys, k=3)
    P.write_scoring_xlsx(score_df, seg, kernel, out)
    return out


def stage_viz(seg: pd.DataFrame, X: np.ndarray, labels: np.ndarray, som,
              mined: dict, model, active_keys: list[str]) -> None:
    from src.lvq import GLVQ
    # per-row mined leaf keys (from the fine cluster each row belongs to)
    cluster2key = {sub["cluster"]: f"{cat['name']} :: {sub['name']}"
                   for cat in mined["categories"] for sub in cat["subcategories"]}
    leaf_keys = np.array([cluster2key.get(int(l), P.MISC_KEY) for l in labels])
    cell_df = viz.som_cell_analysis(som, X, seg["text_unit"].tolist(),
                                    labels=leaf_keys, keys=active_keys)
    viz.write_som_cells(cell_df)
    viz.som_cells_plot(som, som.accumulate_density(X), cell_df)
    viz.som_3d(som, som.accumulate_density(X))
    # hierarchy + volumes for treemap (self-organized 2-level)
    hier = viz.som_hierarchy(cell_df, mined)
    vols = hier.groupby(["category", "subcategory"])["count"].sum().reset_index()
    vols = vols.rename(columns={"count": "volume"})
    viz.treemap(vols)
    viz.taxonomy_tree(mined)
    print("visualizations written to", OUTPUTS_DIR)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--full", action="store_true",
                    help="score the FULL 7-month billing segment (not just the sample)")
    args = ap.parse_args()

    t0 = time.time()
    df = stage_load_data()
    kernel = stage_billing_kernel(df)
    seg, X = stage_billing_segment(df, kernel)
    seed = stage_seed_reconcile()
    table, report = stage_clustering(seg, X)
    labels = stage_fit_clusters(X, table)
    mined = stage_mine(seg, X, labels)
    model, active = stage_glvq(X, labels, mined)
    som = stage_som(X)

    step("Visualizations (treemap, taxonomy tree, SOM topography)")
    stage_viz(seg, X, labels, som, mined, model, active["active_keys"])

    step("Top-3 scoring (sample billing segment)")
    stage_score(seg, X, model, active["active_keys"], kernel,
                OUTPUTS_DIR / "scoring_billing_sample.xlsx")

    if args.full:
        step("FULL 7-month scoring (all billing lines)")
        from scripts.score_ytd import score_full  # noqa: PLC0415
        score_full(df, kernel, model, active["active_keys"])

    print(f"\nDONE in {(time.time() - t0) / 60:.1f} min")
    print("artifacts:", ARTIFACTS_DIR)
    print("outputs:  ", OUTPUTS_DIR)


if __name__ == "__main__":
    main()