"""Step 7: Static HTML BI report generator for tagged Brightspeed billing data.

Consumes a *tagged* workbook (monthly worksheets, or a single tagged sheet with a
date/month column) — the output of the ChatGPT-Excel tagging step — and produces a
single self-contained, static HTML report (Plotly, offline, embedded JS) with:

  * KPI hero strip (total calls, months, categories, fallback share)
  * Month-over-month grouped-bar / line trend by macro category
  * Temporal heatmap: month x macro-category  (volume + share variants)
  * Doughnut / pie "funnel" along a horizontal timeline: one doughnut per month
    showing the category mix (share), months laid out left -> right
  * Optional subcategory trend and per-category breakdown

It works on whatever tagged file the user provides. Input auto-detection:

  * If the workbook has monthly sheets (``Jan_2026`` ... ``Aug_2026``) each with a
    ``ai_tag_1``/``ai_category_1`` and ``Call_Month`` column, those are used directly.
  * If it is a single tagged sheet with ``year_month``/``month``/``Call_Month`` and
    ``category_1``/``ai_category_1`` columns, it is read and grouped by month.

To keep large files fast, the workbook is cached to a parquet keyed by input path.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from plotly.offline import plot as _plot

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "code" / "output"

BRAND = "#512D6D"
PALETTE = [
    "#512D6D", "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf", "#393b79",
]

MONTH_ORDER = [f"{y:04d}-{m:02d}" for y in range(2025, 2027) for m in range(1, 13)]
SHEET_RE = re.compile(r"^(.{3})_(\d{4})$")


def _detect_month_col(df: pd.DataFrame) -> str | None:
    for c in ["Call_Month", "year_month", "month"]:
        if c in df.columns:
            return c
    # derive from a date column
    for c in ["Call_Date", "call_date"]:
        if c in df.columns:
            return None  # handled by caller fallback
    return None


def _norm_month(df: pd.DataFrame, month_col: str | None) -> pd.DataFrame:
    if month_col and month_col in df.columns:
        df["_month"] = df[month_col].astype(str).str[:7]
        return df
    # fall back to a date column
    for date_c in ["Call_Date", "call_date"]:
        if date_c in df.columns:
            s = pd.to_datetime(df[date_c], errors="coerce")
            df["_month"] = s.dt.strftime("%Y-%m")
            return df
    raise SystemExit("no usable month column found in tagged file")


def _resolve_tags(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise parsed tagged rows into _month, _category, _tag, _subcategory."""
    if "_month" not in df.columns:
        mc = _detect_month_col(df)
        df = _norm_month(df, mc)
    for cat_c in ["ai_category_1", "category_1", "category"]:
        if cat_c in df.columns:
            df["_category"] = df[cat_c].fillna("").astype(str).str.strip()
            break
    else:
        raise SystemExit("no category column (ai_category_1/category_1/category) found")
    for tag_c in ["ai_tag_1", "tag_1"]:
        if tag_c in df.columns:
            df["_tag"] = df[tag_c].fillna("").astype(str).str.strip()
            break
    for sub_c in ["ai_subcategory_1", "subcategory_1"]:
        if sub_c in df.columns:
            df["_subcategory"] = df[sub_c].fillna("").astype(str).str.strip()
            break
    return df


def read_tagged(path: Path, cache: bool = True) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return _resolve_tags(pd.read_parquet(path))
    cache_path = OUT / f".cache_{path.stem}.parquet"
    if cache and cache_path.exists():
        return pd.read_parquet(cache_path)
    wb = pd.ExcelFile(path, engine="openpyxl")
    frames = {}
    for s in wb.sheet_names:
        m = SHEET_RE.match(s)
        df = wb.parse(s)
        if m:
            ym = f"{m.group(2)}-{int(m.group(1).lower().replace('jan','01').replace('feb','02').replace('mar','03').replace('apr','04').replace('may','05').replace('jun','06').replace('jul','07').replace('aug','08').replace('sep','09').replace('oct','10').replace('nov','11').replace('dec','12')):02d}"
            df["_month"] = ym
            frames[s] = df
        elif {"year_month", "month", "Call_Month"}.intersection(df.columns):
            frames[s] = df
    wb.close()

    if frames:
        df = pd.concat(list(frames.values()), ignore_index=True, sort=False)
    else:
        df = pd.read_excel(path, engine="openpyxl")

    df = _resolve_tags(df)

    if cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path)
    return df


def _monthly_cat(df: pd.DataFrame) -> pd.DataFrame:
    t = (df.groupby(["_month", "_category"]).size()
          .rename("volume").reset_index())
    t["_month"] = pd.Categorical(t["_month"], MONTH_ORDER, ordered=True)
    t = t.sort_values("_month")
    return t


def _monthly_sub(df: pd.DataFrame) -> pd.DataFrame:
    if "_subcategory" not in df.columns:
        return pd.DataFrame(columns=["_month", "_subcategory", "volume"])
    t = (df.groupby(["_month", "_subcategory"]).size()
         .rename("volume").reset_index())
    t["_month"] = pd.Categorical(t["_month"], MONTH_ORDER, ordered=True)
    return t.sort_values("_month")


# --------------------------------------------------------------------------- charts
def _chart_trend(t: pd.DataFrame) -> go.Figure:
    piv = t.pivot_table(index="_month", columns="_category", values="volume",
                        fill_value=0)
    fig = go.Figure()
    for i, cat in enumerate(piv.columns):
        fig.add_trace(go.Bar(
            x=[str(x) for x in piv.index], y=piv[cat], name=cat,
            marker_color=PALETTE[i % len(PALETTE)],
            hovertemplate="%{x}<br>%{fullData.name}: %{y:,}<extra></extra>",
        ))
    fig.update_layout(barmode="group", height=480,
                      title="Billing & Payments volume by macro category, month over month",
                      xaxis_title="Month", yaxis_title="Calls",
                      legend_orientation="v", paper_bgcolor="white")
    return fig


def _chart_heatmap(t: pd.DataFrame, share: bool) -> go.Figure:
    piv = t.pivot_table(index="_month", columns="_category", values="volume",
                        fill_value=0)
    if share:
        piv = piv.div(piv.sum(axis=1), axis=0).mul(100)
        ztitle = "Share of month (%)"
    else:
        ztitle = "Calls"
    z = piv.values
    ztext = np.where(np.isnan(z), "", np.where(share, np.round(z, 1).astype(str) + "%",
                                               z.astype(int).astype(str)))
    fig = go.Figure(go.Heatmap(
        x=piv.columns, y=[str(x) for x in piv.index], z=z, text=ztext,
        texttemplate="%{text}", colorscale="Purples", zmin=0,
        colorbar_title=ztitle,
        hovertemplate="%{y}<br>%{x}: %{z:,}<extra></extra>",
    ))
    fig.update_layout(height=max(360, 20 * len(piv) + 120),
                      title="Temporal heatmap — month x macro category",
                      yaxis_autorange="reversed", paper_bgcolor="white")
    return fig


def _chart_doughnut_timeline(t: pd.DataFrame) -> go.Figure:
    piv = t.pivot_table(index="_month", columns="_category", values="volume",
                        fill_value=0)
    months = list(piv.index)
    n = len(months)
    # domain slots fraction of width for each doughnut across a horizontal timeline
    slot_w = piv.shape[1]  # number of categories (for the legend)
    fig = make_subplots(rows=1, cols=n,
                        subplot_titles=[str(m) for m in months],
                        specs=[[{"type": "domain"} for _ in range(n)]])
    for j, m in enumerate(months, start=1):
        row = piv.loc[m]
        vals = row[row > 0]
        if vals.empty:
            continue
        fig.add_trace(go.Pie(
            labels=list(vals.index), values=list(vals.values),
            hole=0.42, marker=dict(colors=[PALETTE[i % len(PALETTE)]
                                           for i, _ in enumerate(vals.index)]),
            textinfo="none", hovertemplate="%{label}: %{value:,} (%{percent})<extra></extra>",
            showlegend=(j == 1), name=str(m),
            textposition="inside", insidetextorientation="horizontal",
        ), 1, j)
    fig.update_layout(height=460,
                      title="Month-over-month category mix — doughnut funnel across the timeline",
                      paper_bgcolor="white",
                      legend_orientation="h", legend_yanchor="bottom",
                      legend_y=-0.25)
    return fig


def _chart_subcategory(t: pd.DataFrame) -> go.Figure:
    if t.empty:
        return go.Figure()
    top = (t.groupby("_subcategory")["volume"].sum().nlargest(15).index)
    t = t[t["_subcategory"].isin(top)]
    piv = t.pivot_table(index="_month", columns="_subcategory", values="volume",
                        fill_value=0)
    fig = go.Figure()
    for i, cat in enumerate(piv.columns):
        fig.add_trace(go.Scatter(
            x=[str(x) for x in piv.index], y=piv[cat], name=cat, mode="lines+markers",
            line=dict(width=2, color=PALETTE[i % len(PALETTE)]),
            hovertemplate="%{x}<br>%{fullData.name}: %{y:,}<extra></extra>",
        ))
    fig.update_layout(height=480,
                      title="Top subcategories by volume over time",
                      xaxis_title="Month", yaxis_title="Calls", paper_bgcolor="white")
    return fig


def build_report(path: Path, out: Path | None = None) -> Path:
    out = out or OUT / f"{path.stem}_BI_report.html"
    df = read_tagged(path)
    df = df[df["_category"] != ""]
    t = _monthly_cat(df)
    ts = _monthly_sub(df)

    total = len(df)
    n_months = t["_month"].nunique()
    n_cats = df["_category"].nunique()
    fallback = float((df["_category"] == "Other Category").mean()) * 100

    figs = [
        _chart_trend(t),
        _chart_heatmap(t, share=False),
        _chart_heatmap(t, share=True),
        _chart_doughnut_timeline(t),
        _chart_subcategory(ts),
    ]
    # embed plotly.js exactly once (self-contained static file like the examples);
    # each later figure only emits a newPlot script body.
    divs = [_to_html(f, include_js=(i == 0)) for i, f in enumerate(figs)]
    divs_html = "".join(f'<div class="card">{d}</div>' for d in divs)

    kpis = f"""
    <div class="kpis">
      <div class="kpi"><b>{total:,}</b><br>tagged calls</div>
      <div class="kpi"><b>{n_months}</b><br>months</div>
      <div class="kpi"><b>{n_cats}</b><br>categories</div>
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
<div class="hero"><h1>{out.stem} — billing & payments BI report</h1>
<p>Interactive temporal heatmaps, trend charts, and month-over-month doughnut/pie funnels.</p>
{kpis}</div>
{divs_html}
<div class="note">Static self-contained HTML (Plotly offline). Tagged source: {path.name}. Regenerated {_dt.date.today().isoformat()} — full year Jan&nbsp;-&nbsp;Aug&nbsp;2026 ({total:,} calls).</div>
</div></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(f"BI report written: {out} ({out.stat().st_size/1e6:.1f} MB)")
    return out


def _to_html(fig: go.Figure, include_js: bool) -> str:
    return _plot(fig, output_type="div", include_plotlyjs=include_js,
                 config={"displaylogo": False, "responsive": True})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tagged", type=Path, help="tagged xlsx (monthly worksheets or single sheet)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    build_report(args.tagged, args.out)


if __name__ == "__main__":
    main()
