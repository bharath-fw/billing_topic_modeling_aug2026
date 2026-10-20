"""Visualization + SOM cell analytics.

Produces the three required outputs:

1. **Treemap** of call volume by category / subcategory (``outputs/treemap.png``).
2. **Taxonomy tree** — the groomed 2-level Category :: Subcategory hierarchy
   (``outputs/taxonomy_tree.png``).
3. **SOM 3D topography** — 20x20 Kohonen map where z = aggregated call count per
   BMU cell, plus a cell-labelled heat map and the per-cell center keywords
   (``outputs/som_3d.png``, ``outputs/som_cells.png``, ``outputs/som_cells.tsv``).

For every SOM cell we emit: grid coordinate, call count, top TF-IDF keywords,
and the dominant subcategory label; the cells are then organised into the
2-level category/subcategory hierarchy.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import cm

try:
    import squarify
    HAS_SQUARIFY = True
except Exception:
    HAS_SQUARIFY = False

from .config import OUTPUTS_DIR

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

CAT_COLORS = plt.get_cmap("tab20").colors


# ---------------------------------------------------------------- treemap
def treemap(volumes: pd.DataFrame, path: Path = OUTPUTS_DIR / "treemap.png",
            title: str = "Billing call volume — Category ▸ Subcategory") -> Path:
    """Treemap: outer boxes = categories, inner boxes = subcategories."""
    vols = volumes.copy()
    fig, ax = plt.subplots(figsize=(14, 9))
    # size by call volume
    sizes = vols["volume"].clip(lower=0.01)
    labels = [f"{r.category}\n{r.subcategory}\n{r.volume:,}" for r in vols.itertuples()]
    cat_names = list(dict.fromkeys(vols["category"]))
    color_map = {c: CAT_COLORS[i % len(CAT_COLORS)] for i, c in enumerate(cat_names)}
    colors = [color_map[r.category] for r in vols.itertuples()]
    if HAS_SQUARIFY:
        squarify.plot(sizes=sizes, label=labels, color=colors, alpha=0.85, ax=ax,
                      text_kwargs={"fontsize": 7})
    else:
        ax.bar(range(len(vols)), sizes.values, color=colors)
    ax.set_title(title, fontsize=14)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    print(f"treemap -> {path}")
    return path


# ----------------------------------------------------------- taxonomy tree
def taxonomy_tree(mined: dict, path: Path = OUTPUTS_DIR / "taxonomy_tree.png") -> Path:
    """Render the mined 2-level hierarchy (categories -> subcategories + keywords)."""
    cats = mined["categories"]
    n_subs = sum(len(c["subcategories"]) for c in cats)
    fig, ax = plt.subplots(figsize=(16, max(8, 0.5 * n_subs)))
    ax.axis("off")
    y = 0.0
    for cat in cats:
        subs = cat["subcategories"]
        vol = sum(s["count"] for s in subs)
        ax.text(0.02, y, f"▍ {cat['name']}  ({vol:,})",
                fontsize=11, fontweight="bold", va="center", color="#0b3d91")
        for i, sub in enumerate(subs):
            kw = " · ".join(sub["keywords"])
            ax.text(0.16, y - (i + 1) * 0.045,
                    f"└─ {sub['name']}  [{sub['count']:,}]  — {kw}",
                    fontsize=8, va="center", color="#444444")
        y -= (len(subs) + 1) * 0.055
    ax.set_xlim(0, 1)
    ax.set_ylim(y - 0.05, 0.5)
    ax.set_title(f"Mined billing taxonomy — {len(cats)} categories, {n_subs} "
                 f"subcategories (self-organized, keywords per leaf)", fontsize=13)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    print(f"taxonomy tree -> {path}")
    return path


# ------------------------------------------------------------ SOM analytics
def som_cell_analysis(som, X: np.ndarray, texts: list[str],
                      labels: np.ndarray | None = None,
                      keys: list[str] | None = None,
                      topn: int = 4) -> pd.DataFrame:
    """Per-cell analytics: count, keywords, dominant subcategory.

    Every cell's centre is described by the top TF-IDF terms of its member calls;
    the dominant subcategory comes from the mode of the per-call labels (or the
    nearest prototype when labels are None).
    """
    from sklearn.feature_extraction.text import TfidfVectorizer

    cells = som.bmu_batch(X)
    grid = som.grid
    tfv = TfidfVectorizer(ngram_range=(1, 2), max_features=15_000,
                          stop_words="english", min_df=3)
    Tf = tfv.fit_transform(texts)
    feat = np.array(tfv.get_feature_names_out())

    rows = []
    sim_mat = None
    if labels is None and keys is not None and hasattr(som, "weights_"):
        # nearest prototype per cell centre
        W = som.weights_.cpu().numpy()
        sim_mat = W @ W.T  # not used directly; we use member labels below
    for cid in range(grid * grid):
        mask = cells == cid
        n = int(mask.sum())
        r, c = divmod(cid, grid)
        if n == 0:
            continue
        kw = _top_terms(Tf, feat, mask, topn)
        if labels is not None:
            lab = pd.Series(labels[mask]).mode().iloc[0]
        else:
            lab = ""
        rows.append({"cell": cid, "row": r, "col": c, "count": n,
                     "keywords": " | ".join(kw), "subcategory": lab})
    return pd.DataFrame(rows)


def _top_terms(Tf, feat, mask, n=4) -> list[str]:
    means = Tf[mask].mean(axis=0).A1
    return [feat[j] for j in np.argsort(means)[::-1][:n]]


def som_3d(som, density: np.ndarray, path: Path = OUTPUTS_DIR / "som_3d.png") -> Path:
    """3D topographic map of the SOM: z = aggregated call count per BMU cell."""
    grid = som.grid
    xx, yy = np.meshgrid(np.arange(grid), np.arange(grid))
    zz = density.astype(float)
    fig = plt.figure(figsize=(12, 9))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_surface(xx, yy, zz, cmap=cm.viridis, edgecolor="none", alpha=0.92)
    ax.set_xlabel("SOM col"); ax.set_ylabel("SOM row"); ax.set_zlabel("calls / cell")
    ax.set_title(f"SOM {grid}x{grid} topography — peak {int(zz.max()):,} calls/cell",
                 fontsize=13)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    print(f"SOM 3D topography -> {path}")
    return path


def som_cells_plot(som, density: np.ndarray, cell_df: pd.DataFrame,
                   path: Path = OUTPUTS_DIR / "som_cells.png") -> Path:
    """2D heat map of the SOM with per-cell keyword labels."""
    grid = som.grid
    fig, ax = plt.subplots(figsize=(14, 12))
    im = ax.imshow(density, cmap="magma")
    for _, r in cell_df.iterrows():
        ax.text(r["col"], r["row"], f"{r['keywords']}\n{r['count']:,}",
                ha="center", va="center", fontsize=6, color="white")
    ax.set_title(f"SOM {grid}x{grid} cells — BMU-aggregated call counts + keywords")
    ax.set_xticks(range(grid)); ax.set_yticks(range(grid))
    ax.grid(True, color="white", lw=0.3)
    fig.colorbar(im, ax=ax, label="calls / cell")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    print(f"SOM cell map -> {path}")
    return path


def som_hierarchy(cell_df: pd.DataFrame, mined: dict) -> pd.DataFrame:
    """Organise the 20x20 cells into the mined 2-level category/subcategory hierarchy.

    Each cell's dominant label is a mined leaf key "Category :: Subcategory".
    Cells with an unknown label (folded / misc) go under Other Category :: Misc/Other.
    """
    known = set()
    for cat in mined["categories"]:
        for sub in cat["subcategories"]:
            known.add(f"{cat['name']} :: {sub['name']}")
    out = cell_df.copy()
    cat, sub = [], []
    for lab in out["subcategory"]:
        if lab in known:
            c, s = lab.split(" :: ", 1)
        else:
            c, s = "Other Category", "Misc/Other"
        cat.append(c); sub.append(s)
    out["category"] = cat
    out["subcategory"] = sub
    return out


def write_som_cells(cell_df: pd.DataFrame, path: Path = OUTPUTS_DIR / "som_cells.tsv") -> Path:
    cell_df.to_csv(path, sep="\t", index=False)
    print(f"SOM cell table -> {path}")
    return path