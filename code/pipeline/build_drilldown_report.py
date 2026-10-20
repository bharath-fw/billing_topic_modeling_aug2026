"""Interactive drill-down BI report for Brightspeed billing & payments.

Single self-contained HTML (Plotly offline, embedded once):

  * KPI hero strip (total calls, months, categories, fallback share)
  * Category selector strip ("All Categories" + one button per macro category)
  * Selecting a category shows, for THAT category only:
      - MoM line/trend of each of its subcategories
      - month x subcategory heatmap (volume)
      - month-over-month doughnut timeline (top-6 + Other) for its subcategories
  * "All Categories" view = the macro-category overview (trend, heatmap, doughnut)

All figures are pre-computed in Python, embedded as JSON, and driven client-side
with Plotly.react so each drill-down view stays small (a category has 6-17 leaves).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from plotly.offline import get_plotlyjs

from report import read_tagged, MONTH_ORDER, PALETTE, BRAND

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "code" / "output"

DEFAULT_NAME = "Brightspeed_Billing_Drilldown_BI_Report.html"
OVERVIEW_NAME = "All Categories"
DOUGHNUT_TOPN = 6
OTHER_NAME = "Other"


# ---------------------------------------------------------------- figure builders
def _months_used(df: pd.DataFrame) -> list[str]:
    return [m for m in MONTH_ORDER if m in set(df["_month"])]


def _pivot(df: pd.DataFrame, col: str, months: list[str]) -> pd.DataFrame:
    t = df.groupby(["_month", col]).size().rename("volume").reset_index()
    t["_month"] = pd.Categorical(t["_month"], MONTH_ORDER, ordered=True)
    piv = t.pivot_table(index="_month", columns=col, values="volume",
                        fill_value=0).reindex(months).fillna(0)
    order = piv.sum().sort_values(ascending=False).index.tolist()
    return piv[order]


def trend_fig(piv: pd.DataFrame, title: str) -> dict:
    fig = go.Figure()
    for i, col in enumerate(piv.columns):
        fig.add_trace(go.Scatter(
            x=[str(m) for m in piv.index], y=list(piv[col]), name=col,
            mode="lines+markers",
            line=dict(width=2.5, color=PALETTE[i % len(PALETTE)]),
            marker=dict(size=6),
            hovertemplate="%{x}<br>%{fullData.name}: %{y:,}<extra></extra>",
        ))
    fig.update_layout(height=440, title=title, xaxis_title="Month",
                      yaxis_title="Calls", paper_bgcolor="white",
                      legend=dict(x=1.02, y=1, orientation="v", font=dict(size=11)),
                      margin=dict(r=180))
    return fig.to_plotly_json()


def heatmap_fig(piv: pd.DataFrame, title: str) -> dict:
    z = piv.values.astype(float).tolist()
    ztext = np.where(np.array(z) > 0, np.array(z).round(0).astype(int).astype(str), "").tolist()
    fig = go.Figure(go.Heatmap(
        x=list(piv.columns), y=[str(m) for m in piv.index], z=z, text=ztext,
        texttemplate="%{text}", colorscale="Purples", zmin=0,
        colorbar_title="Calls",
        hovertemplate="%{y}<br>%{x}: %{z:,.0f}<extra></extra>",
    ))
    fig.update_layout(height=max(360, 22 * len(piv) + 160), title=title,
                      yaxis_autorange="reversed", paper_bgcolor="white",
                      xaxis=dict(tickangle=-30), margin=dict(r=0))
    return fig.to_plotly_json()


def donut_fig(piv: pd.DataFrame, title: str) -> dict:
    months = list(piv.index)
    n = len(months)
    fig = make_subplots(rows=1, cols=n,
                        subplot_titles=[str(m) for m in months],
                        specs=[[{"type": "domain"} for _ in range(n)]])
    for j, m in enumerate(months, start=1):
        row = piv.loc[m].sort_values(ascending=False)
        if row.sum() <= 0:
            continue
        top = row.drop(index=OTHER_NAME) if OTHER_NAME in row.index else row
        top = top.nlargest(DOUGHNUT_TOPN)
        slices = list(top.items())
        rest = row[~row.index.isin(top.index)]
        if rest.sum() > 0:
            slices.append((OTHER_NAME, float(rest.sum())))
        fig.add_trace(go.Pie(
            labels=[s[0] for s in slices], values=[float(s[1]) for s in slices],
            hole=0.42,
            marker=dict(colors=[PALETTE[i % len(PALETTE)]
                                for i, _ in enumerate(slices)]),
            textinfo="none", hovertemplate="%{label}: %{value:,} (%{percent})<extra></extra>",
            showlegend=(j == 1), name=str(m),
        ), 1, j)
    fig.update_layout(height=420, title=title, paper_bgcolor="white",
                      legend_orientation="h", legend_yanchor="bottom",
                      legend_y=-0.35, margin=dict(r=0))
    return fig.to_plotly_json()


def build_figures(df: pd.DataFrame) -> tuple[dict, dict]:
    months = _months_used(df)
    cats = [c for c in df["_category"].value_counts().index]
    figs: dict[str, dict] = {}

    all_piv = _pivot(df, "_category", months)
    figs[OVERVIEW_NAME] = {
        "trend": trend_fig(all_piv, "Billing & Payments volume by macro category, month over month"),
        "heat": heatmap_fig(all_piv, "Macro category heatmap — month x category (volume)"),
        "donut": donut_fig(all_piv, "Month-over-month macro category mix — doughnut timeline (top-6 + Other)"),
    }

    cat_meta = {}
    for cat in cats:
        sub = df[df["_category"] == cat]
        piv = _pivot(sub, "_subcategory", months)
        figs[cat] = {
            "trend": trend_fig(piv, f"{cat} — subcategory volume, month over month"),
            "heat": heatmap_fig(piv, f"{cat} — month x subcategory heatmap (volume)"),
            "donut": donut_fig(piv, f"{cat} — month-over-month subcategory mix (top-{DOUGHNUT_TOPN} + Other)"),
        }
        cat_meta[cat] = {"calls": int(len(sub)), "subs": int(piv.shape[1])}
    return figs, cat_meta


# ------------------------------------------------------------------------- export
def build_drilldown(path: Path, out: Path | None = None) -> Path:
    out = out or OUT / DEFAULT_NAME
    df = read_tagged(path)
    df = df[df["_category"] != ""]
    fig, cat_meta = build_figures(df)

    total = int(len(df))
    n_months = df["_month"].nunique()
    n_cats = df["_category"].nunique()
    fallback = float((df["_category"] == "Other Category").mean()) * 100
    cats = [c for c in df["_category"].value_counts().index]

    fig_json = json.dumps(fig, allow_nan=False)
    meta_json = json.dumps({c: {**cat_meta[c], "share": round(100 * cat_meta[c]["calls"] / total, 2)}
                            for c in cats}, allow_nan=False)
    months_json = json.dumps([str(m) for m in _months_used(df)])

    buttons = "".join(
        f'<button class="catbtn active" data-cat="{json.dumps(OVERVIEW_NAME)[1:-1]}">'
        f'All Categories <span class="dim">({total:,})</span></button>'
        + "".join(
            f'<button class="catbtn" data-cat="{json.dumps(c)[1:-1]}">{c} '
            f'<span class="dim">({cat_meta[c]["calls"]:,})</span></button>'
            for c in cats))

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{out.stem} BI report</title>
<style>
body{{font-family:Arial,sans-serif;margin:0;background:#f6f7f8;color:#222}}
.wrap{{max-width:1500px;margin:0 auto;padding:28px}}
.hero{{background:white;padding:22px 30px;border-left:7px solid {BRAND};border-radius:12px}}
h1{{margin:0 0 6px;font-size:28px}} p{{margin:4px 0;color:#555}}
.note{{font-size:12px;color:#777;padding:8px 18px 18px}}
.card{{background:white;border-radius:12px;margin:16px 0;padding:8px 12px;box-shadow:0 1px 5px rgba(0,0,0,.08)}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap;margin-top:14px}}
.kpi{{background:#f3f0f6;border-radius:9px;padding:11px 16px;min-width:150px}}
.kpi b{{font-size:20px;color:{BRAND}}}
.catsel{{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 4px}}
.catbtn{{border:1px solid #d5c8df;background:#fff;color:#512D6D;border-radius:18px;
padding:7px 14px;font-size:13px;cursor:pointer}}
.catbtn:hover{{background:#f3eef8}}
.catbtn.active{{background:#512D6D;color:#fff;border-color:#512D6D}}
.dim{{opacity:.6;font-size:11px}}
.cur{{font-size:15px;color:#512D6D;font-weight:bold;margin:4px 2px 0}}
</style></head><body><div class="wrap">
<div class="hero"><h1>{out.stem} — billing &amp; payments drill-down BI report</h1>
<p>Click a macro category to drill into its subcategory trend, heatmap and monthly mix; default view is the full macro-category overview.</p>
<div class="kpis">
  <div class="kpi"><b>{total:,}</b><br>tagged calls</div>
  <div class="kpi"><b>{n_months}</b><br>months</div>
  <div class="kpi"><b>{n_cats}</b><br>categories</div>
  <div class="kpi"><b>{fallback:.1f}%</b><br>Other / fallback</div>
  <div class="kpi"><b id="kCalls">-</b><br>category calls</div>
  <div class="kpi"><b id="kShare">-</b><br>share of total</div>
  <div class="kpi"><b id="kSubs">-</b><br>subcategories</div>
</div>
<div class="catsel" id="catsel">{buttons}</div>
<div class="cur" id="cur">{OVERVIEW_NAME}</div>
<div class="card" id="cardTrend"></div>
<div class="card" id="cardHeat"></div>
<div class="card" id="cardDonut"></div>
<div class="note">Static self-contained HTML (Plotly offline). Tagged source: {path.name}. Regenerated {_dt.date.today().isoformat()} — full year Jan&nbsp;-&nbsp;Aug&nbsp;2026 ({total:,} calls).</div>
</div>
<script>window.PlotlyConfig = {{MathJaxConfig: 'local'}};</script>
<script type="text/javascript">{get_plotlyjs()}</script>
<script>
const months = {months_json};
const FIGS = {fig_json};
const METAS = {meta_json};
const OVERVIEW = {json.dumps(OVERVIEW_NAME)};
const TOTAL = {total};
const rc = (el, fig) => Plotly.react(el, JSON.parse(JSON.stringify(fig)),
    {{displaylogo:false, responsive:true}});
const fmt = n => n.toLocaleString('en-US');
function select(cat){{
  const f = FIGS[cat];
  const k = cat === OVERVIEW ? {{calls: TOTAL, share: 100.0,
      subs: Object.keys(METAS).length}} : METAS[cat];
  rc('cardTrend', f.trend);
  rc('cardHeat', f.heat);
  rc('cardDonut', f.donut);
  document.getElementById('cur').textContent = cat;
  document.getElementById('kCalls').textContent = fmt(k.calls);
  document.getElementById('kShare').textContent = k.share.toFixed(2) + '%';
  document.getElementById('kSubs').textContent = k.subs;
  document.querySelectorAll('.catbtn').forEach(b =>
    b.classList.toggle('active', b.dataset.cat === cat));
}}
document.getElementById('catsel').addEventListener('click', e => {{
  const b = e.target.closest('button[data-cat]');
  if (b) select(b.dataset.cat);
}});
select(OVERVIEW);
</script>
</body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(f"Drill-down BI report written: {out} ({out.stat().st_size/1e6:.1f} MB)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tagged", type=Path, help="tagged xlsx/parquet")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    build_drilldown(args.tagged, args.out)


if __name__ == "__main__":
    main()