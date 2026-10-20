"""Subcategory BI report: same self-contained static HTML style as the category
report, but at subcategory (leaf) granularity with a top-N rollup.

Keeps the visual clean by charting only the top N subcategories by full-period
volume and folding the long tail into an "Other subcategories" aggregate:

  * KPI hero strip (calls, months, subcategories shown, tail share, fallback)
  * Top-N - subcategory line/trend across the months
  * Heatmaps: month x top-N subcategory (volume + share variants)
  * Doughnut timeline: per-month top-8 mix (+ Other for the tail)
"""
from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from plotly.offline import plot as _plot

from report import read_tagged, _monthly_sub, MONTH_ORDER, PALETTE, BRAND

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "code" / "output"

DEFAULT_NAME = "Brightspeed_Billing_Subcategory_BI_Report.html"
TOP_N = 20          # subcategories shown per chart after the Other rollup
DOUGHNUT_TOPN = 8   # per-month slices before the Other rollup
OTHER_NAME = "Other subcategories"


def top_label(n: int | None = None) -> str:
    return f"Top {n or TOP_N}"


def pivot_top(df: pd.DataFrame, top_n: int = TOP_N) -> tuple[pd.DataFrame, list[str]]:
    """Return (pivot month x subcategory-of-top-N-plus-Other, ordered names)."""
    sub = df[df["_subcategory"] != ""]
    top = sub.groupby("_subcategory")["volume"].sum().nlargest(top_n).index.tolist()
    s = sub.copy()
    s.loc[~s["_subcategory"].isin(top), "_subcategory"] = OTHER_NAME
    t = s.groupby(["_month", "_subcategory"], as_index=False)["volume"].sum()
    t["_month"] = pd.Categorical(t["_month"], MONTH_ORDER, ordered=True)
    t = t.sort_values("_month")
    order = top + [OTHER_NAME]
    piv = t.pivot_table(index="_month", columns="_subcategory", values="volume",
                        fill_value=0)[order]
    return piv, order


def _chart_trend(piv: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for i, sub in enumerate(piv.columns):
        dash = "dot" if sub == OTHER_NAME else "solid"
        width = 1.6 if sub != OTHER_NAME else 1.2
        fig.add_trace(go.Scatter(
            x=[str(m) for m in piv.index], y=piv[sub], name=sub,
            mode="lines+markers",
            line=dict(width=width, dash=dash, color=PALETTE[i % len(PALETTE)]),
            marker=dict(size=7),
            hovertemplate="%{x}<br>%{fullData.name}: %{y:,}<extra></extra>",
        ))
    fig.update_layout(height=560, barmode="group",
                      title=f"Billing & Payments volume by top-{len(piv.columns)-1} subcategory (month over month)",
                      xaxis_title="Month", yaxis_title="Calls",
                      legend_orientation="v", paper_bgcolor="white",
                      legend=dict(x=1.02, y=1, itemsizing="trace", tracegroupgap=0))
    fig.update_xaxes(autorange=False)
    return fig


def _chart_heatmap(piv: pd.DataFrame, share: bool) -> go.Figure:
    z = piv.values
    if share:
        z = z / z.sum(axis=1, keepdims=True) * 100
        ztitle, digits = "Share of month (%)", 1
    else:
        ztitle, digits = "Calls", 0
    ztext = np.where(np.isnan(z), "",
                     np.where(share, z.round(1).astype(str) + "%",
                              z.round(0).astype(int).astype(str)))
    hovert = ("%{y}<br>%{x}: %{z:,.1f}%<extra></extra>" if share
              else "%{y}<br>%{x}: %{z:,.0f}<extra></extra>")
    fig = go.Figure(go.Heatmap(
        x=piv.columns, y=[str(m) for m in piv.index], z=z, text=ztext,
        texttemplate="%{text}", colorscale="Purples", zmin=0,
        colorbar_title=ztitle,
        hovertemplate=hovert,
    ))
    fig.update_layout(height=max(560, 22 * len(piv) + 180),
                      title=("Subcategory heatmap — month x subcategory (share %)"
                             if share else
                             "Subcategory heatmap — month x subcategory (volume)"),
                      yaxis_autorange="reversed", paper_bgcolor="white")
    return fig


def _chart_doughnut_timeline(piv: pd.DataFrame) -> go.Figure:
    months = list(piv.index)
    n = len(months)
    fig = make_subplots(rows=1, cols=n,
                        subplot_titles=[str(m) for m in months],
                        specs=[[{"type": "domain"} for _ in range(n)]])
    for j, m in enumerate(months, start=1):
        row = piv.loc[m]
        # top-DOUGHNUT_TOPN + Other, re-ranked per month
        vals = row.sort_values(ascending=False)
        if OTHER_NAME in vals.index:
            rest = vals.drop(OTHER_NAME).nlargest(DOUGHNUT_TOPN).copy()
            tail = vals[~vals.index.isin(rest.index)]
            if tail.sum() > 0:
                rest.loc[OTHER_NAME] = tail.sum()
            vals = rest
        else:
            vals = vals.nlargest(DOUGHNUT_TOPN)
        if vals.empty:
            continue
        fig.add_trace(go.Pie(
            labels=list(vals.index), values=list(vals.values),
            hole=0.42,
            marker=dict(colors=[PALETTE[i % len(PALETTE)]
                                for i, _ in enumerate(vals.index)]),
            textinfo="none", hovertemplate="%{label}: %{value:,} (%{percent})<extra></extra>",
            showlegend=(j == 1), name=str(m),
            textposition="inside", insidetextorientation="horizontal",
        ), 1, j)
    fig.update_layout(height=500,
                      title="Month-over-month subcategory mix — doughnut timeline (top-8 + Other)",
                      paper_bgcolor="white",
                      legend_orientation="h", legend_yanchor="bottom",
                      legend_y=-0.32)
    return fig


def build_subcategory_report(path: Path, out: Path | None = None,
                             top_n: int = TOP_N) -> Path:
    out = out or OUT / DEFAULT_NAME
    df = read_tagged(path)
    df = df[df["_category"] != ""]
    ts = _monthly_sub(df)
    ts = ts[ts["_subcategory"] != ""]

    total = len(df)
    n_months = ts["_month"].nunique()
    n_unique_sub = df["_subcategory"].replace("", "Other").nunique()
    fallback = float((df["_category"] == "Other Category").mean()) * 100

    piv, order = pivot_top(ts, top_n=top_n)
    tail_share = 100 * piv[OTHER_NAME].sum() / max(piv.sum().sum(), 1)

    figs = [
        _chart_trend(piv),
        _chart_heatmap(piv, share=False),
        _chart_heatmap(piv, share=True),
        _chart_doughnut_timeline(piv),
    ]
    divs = [_to_html(f, include_js=(i == 0)) for i, f in enumerate(figs)]
    divs_html = "".join(f'<div class="card">{d}</div>' for d in divs)

    kpis = f"""
    <div class="kpis">
      <div class="kpi"><b>{total:,}</b><br>tagged calls</div>
      <div class="kpi"><b>{n_months}</b><br>months</div>
      <div class="kpi"><b>{top_n}</b><br>subcategories shown</div>
      <div class="kpi"><b>{tail_share:.1f}%</b><br>Other / tail share</div>
      <div class="kpi"><b>{fallback:.1f}%</b><br>Other / fallback</div>
    </div>
    """

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{out.stem} BI report</title>
<style>
body{{font-family:Arial,sans-serif;margin:0;background:#f6f7f8;color:#222}}
.wrap{{max-width:1500px;margin:0 auto;padding:28px}}
.card{{background:white;border-radius:12px;margin:18px 0;padding:8px 12px;box-shadow:0 1px 5px rgba(0,0,0,.08)}}
.hero{{background:white;padding:24px 30px;border-left:7px solid {BRAND};border-radius:12px}}
h1{{margin:0 0 8px;font-size:30px}} p{{margin:6px 0;color:#555}}
.note{{font-size:12px;color:#777;padding:8px 18px 18px}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap;margin-top:18px}}
.kpi{{background:#f3f0f6;border-radius:9px;padding:11px 16px;min-width:150px}}
.kpi b{{font-size:20px;color:{BRAND}}}
</style></head><body><div class="wrap">
<div class="hero"><h1>{out.stem} — billing & payments subcategory BI report</h1>
<p>Top-{top_n} subcategories across the full year; the long tail ({n_unique_sub - top_n} others) is folded into "{OTHER_NAME}".</p>
{kpis}</div>
{divs_html}
<div class="note">Static self-contained HTML (Plotly offline). Tagged source: {path.name}. Regenerated {_dt.date.today().isoformat()} — full year Jan&nbsp;-&nbsp;Aug&nbsp;2026 ({total:,} calls).</div>
</div></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(f"Subcategory BI report written: {out} ({out.stat().st_size/1e6:.1f} MB)")
    return out


def _to_html(fig: go.Figure, include_js: bool) -> str:
    return _plot(fig, output_type="div", include_plotlyjs=include_js,
                 config={"displaylogo": False, "responsive": True})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tagged", type=Path, help="tagged xlsx/parquet (monthly worksheets or single sheet)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--top-n", type=int, default=TOP_N,
                    help=f"subcategories to chart before Other rollup (default {TOP_N})")
    args = ap.parse_args()
    build_subcategory_report(args.tagged, args.out, top_n=args.top_n)


if __name__ == "__main__":
    main()