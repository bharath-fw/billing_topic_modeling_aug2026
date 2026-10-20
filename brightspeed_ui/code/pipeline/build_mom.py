"""Regenerate the Brightspeed month-over-month (MoM) deliverable files.

Consumes the FULL-YEAR tagged parquet (``code/output/billing_tagged_full.parquet``,
ai_tag_1/ai_category_1/ai_subcategory_1 schema) produced by :mod:`autotag` from the
existing (frozen) 104-leaf billing taxonomy -- no taxonomy re-mining, ML-only scoring.

Writes three self-contained deliverables into ``code/output``:

  * ``brightspeed_mom_final_tagged_counts.csv``
        month,category,volume,share_pct  (one row per category per month, Jan..Aug)

  * ``Brightspeed_MoM_Category_Pie_Funnel.html``
        Self-contained interactive HTML (Plotly offline) with:
          - a horizontal timeline of per-month doughnut (pie) funnels
          - month-over-month category trend lines (share %)
          - monthly total billing-call bars

  * ``Brightspeed_MoM_Subcategory_Pie_Funnel.html``
        Self-contained interactive HTML with a category dropdown drive:
          - per-month subcategory doughnut funnels (area-scaled)
          - top-leaf MoM share trend lines
          - top-leaf mix-shift heatmap

All titles / KPI strips are dated to the current refresh (Sep 2026, full Jan-Aug year).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from plotly.offline import plot as _plot

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "code" / "output"

BRAND = "#512D6D"
REFRESH = "Sep 2026"
MONTH_RANGE = "Jan 2026 - Aug 2026"

CAT_PALETTE = [
    "#512D6D", "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]

MONTH_NAMES = {i: m for i, m in enumerate([
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
    "Sep", "Oct", "Nov", "Dec"], start=1)}

MONTH_RANGE_JS = json.dumps(MONTH_RANGE)


def _month_order(df: pd.DataFrame, col: str = "Call_Month") -> list[str]:
    return sorted(df[col].dropna().unique())


def _month_label(ym: str) -> str:
    try:
        return MONTH_NAMES[int(ym.split("-")[1])]
    except Exception:
        return ym


# --------------------------------------------------------------------------- data
def load_tagged(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["Call_Month"] = df["Call_Month"].astype(str).str[:7]
    for c in ["ai_category_1", "ai_subcategory_1", "ai_tag_1"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str).str.strip()
    # only keep genuinely scored (non-empty) primary categories
    return df[df["ai_category_1"] != ""].reset_index(drop=True)


def monthly_category(df: pd.DataFrame) -> pd.DataFrame:
    t = (df.groupby(["Call_Month", "ai_category_1"]).size()
         .rename("volume").reset_index())
    return t


def monthly_counts_csv(df: pd.DataFrame) -> pd.DataFrame:
    t = monthly_category(df)
    total = t.groupby("Call_Month")["volume"].transform("sum")
    t["share_pct"] = (100 * t["volume"] / total)
    return t[["Call_Month", "ai_category_1", "volume", "share_pct"]] \
        .rename(columns={"Call_Month": "month", "ai_category_1": "category"})


def monthly_subcategory(df: pd.DataFrame) -> pd.DataFrame:
    t = (df.groupby(["Call_Month", "ai_category_1", "ai_subcategory_1",
                     "ai_tag_1"]).size().rename("calls").reset_index())
    return t


# ----------------------------------------------------------------------- category
def build_category_funnel(df: pd.DataFrame, months: list[str]) -> go.Figure:
    # one doughnut per month across a horizontal timeline (area-scaled)
    cat_order = sorted(df["ai_category_1"].unique(),
                       key=lambda c: -df[df["ai_category_1"] == c].shape[0])
    month_total = df.groupby("Call_Month").size()
    month_share = (df.groupby(["Call_Month", "ai_category_1"]).size().unstack(fill_value=0)
                   .div(month_total, axis=0))

    n = len(months)
    fig = make_subplots(rows=1, cols=n, specs=[[{"type": "domain"} for _ in range(n)]],
                        subplot_titles=[_month_label(m) for m in months])
    max_pop = month_total.max()
    for j, m in enumerate(months, start=1):
        pop = int(month_total.get(m, 0))
        scale = (pop / max_pop) ** 0.5
        row = month_share.loc[m][month_share.loc[m] > 0].sort_values(ascending=False)
        if row.empty:
            continue
        # widen/shrink the domain based on pop so bigger months get bigger doughnuts
        row_dom = 0.62 + 0.34 * scale
        x0 = 0.5 - row_dom / 2
        x1 = 0.5 + row_dom / 2
        fig.add_trace(go.Pie(
            labels=list(row.index), values=np.round(100 * row.values, 2).tolist(),
            hole=0.43, sort=False, direction="clockwise",
            textinfo="none",
            customdata=[[m, _month_label(m), pop, c] for c in row.index],
            hovertemplate="<b>%{label}</b><br>Month: %{customdata[1]} %{customdata[3]}"
                          "<br>Volume: %{customdata[2]:,}<br>Share: %{value:.1f}%"
                          "<extra></extra>",
            marker=dict(colors=[CAT_PALETTE[i % len(CAT_PALETTE)]
                                for i in range(len(row))],
                        line=dict(color="white", width=1)),
            showlegend=(j == 1), name=_month_label(m),
            domain=dict(x=[x0, x1], y=[0.05, 0.99]),
        ), 1, j)
    fig.update_layout(
        height=660,
        title=dict(text="Brightspeed billing category mix, month over month "
                        f"({MONTH_RANGE})", x=0.02, font=dict(size=19)),
        paper_bgcolor="#fff", plot_bgcolor="#fff",
        margin=dict(l=20, r=20, t=60, b=30),
        legend_orientation="v", legend=dict(x=1.01, y=1.0),
        annotations=[
            dict(x=0.02, y=0.02, xref="paper", yref="paper", showarrow=False,
                 text=f"{REFRESH} refresh - full year", font=dict(size=11, color="#777"),
                 xanchor="left"),
        ])
    return fig


def build_category_trend(df: pd.DataFrame, months: list[str]) -> go.Figure:
    month_total = df.groupby("Call_Month").size()
    share = (df.groupby(["Call_Month", "ai_category_1"]).size().unstack(fill_value=0)
             .div(month_total, axis=0).mul(100))
    cat_order = sorted(df["ai_category_1"].unique(),
                       key=lambda c: -df[df["ai_category_1"] == c].shape[0])
    fig = go.Figure()
    xs = [_month_label(m) for m in months]
    for i, cat in enumerate(cat_order):
        y = [share.loc[m, cat] if m in share.index and cat in share.columns else 0
             for m in months]
        yy = []
        custom = []
        for m in months:
            n = share.loc[m, cat] if m in share.index and cat in share.columns else 0
            yy.append(n)
            vol = int(df[(df.Call_Month == m) & (df.ai_category_1 == cat)].shape[0])
            custom.append([vol, f"{n:.1f}%"])
        fig.add_trace(go.Scatter(
            x=xs, y=yy, name=cat, mode="lines+markers",
            line=dict(width=3, color=CAT_PALETTE[i % len(CAT_PALETTE)]),
            marker=dict(size=7),
            customdata=custom,
            hovertemplate="<b>%{fullData.name}</b><br>Month: %{x}"
                          "<br>Volume: %{customdata[0]:,}<br>Share: %{customdata[1]}"
                          "<extra></extra>",
        ))
    fig.update_layout(height=560,
                      title=dict(text="Monthly share trend by macro category", x=0.02,
                                 font=dict(size=18)),
                      yaxis=dict(title="Share of billing calls (%)", ticksuffix="%"),
                      xaxis=dict(title=""),
                      legend_orientation="h", legend=dict(y=-0.22),
                      margin=dict(l=70, r=30, t=55, b=90),
                      hovermode="x unified", paper_bgcolor="#fff", plot_bgcolor="#fff")
    return fig


def build_month_total_bars(df: pd.DataFrame, months: list[str]) -> go.Figure:
    totals = df.groupby("Call_Month").size()
    fig = go.Figure(go.Bar(
        x=[_month_label(m) for m in months],
        y=[int(totals.get(m, 0)) for m in months],
        marker_color=BRAND,
        text=[f"{int(totals.get(m, 0)):,}" for m in months],
        textposition="outside",
        hovertemplate="Month: %{x}<br>Billing calls: %{y:,}<extra></extra>",
    ))
    fig.update_layout(height=430,
                      title=dict(text="Monthly billing call volume", x=0.02,
                                 font=dict(size=18)),
                      xaxis=dict(title=""), yaxis=dict(title="Billing calls"),
                      margin=dict(l=60, r=30, t=55, b=50),
                      paper_bgcolor="#fff", plot_bgcolor="#fff")
    return fig


def _to_html(fig: go.Figure, include_js: bool) -> str:
    return _plot(fig, output_type="div", include_plotlyjs=include_js,
                 config={"displaylogo": False, "responsive": True})


def write_category_html(df: pd.DataFrame, months: list[str],
                        out_path: Path, total: int) -> Path:
    n_cats = df["ai_category_1"].nunique()
    fallback = 100 * (df["ai_category_1"] == "Other Category").mean()
    figs = [build_category_funnel(df, months),
            build_category_trend(df, months),
            build_month_total_bars(df, months)]
    divs = [_to_html(f, include_js=(i == 0)) for i, f in enumerate(figs)]
    divs_html = "".join(f'<div class="card">{d}</div>' for d in divs)
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Brightspeed MoM Billing Category Funnel</title>
<style>
body{{font-family:Arial,sans-serif;margin:0;background:#f6f7f8;color:#222}}
.wrap{{max-width:1500px;margin:0 auto;padding:28px}}
.card{{background:white;border-radius:12px;margin:18px 0;padding:8px 12px;box-shadow:0 1px 5px rgba(0,0,0,.08)}}
.hero{{background:white;padding:24px 30px;border-left:7px solid {BRAND};border-radius:12px}}
h1{{margin:0 0 8px;font-size:30px}} p{{margin:6px 0;color:#555}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap;margin-top:18px}}
.kpi{{background:#f3f0f6;border-radius:9px;padding:11px 16px;min-width:150px}}
.kpi b{{font-size:20px;color:{BRAND}}}
.note{{font-size:12px;color:#777;padding:8px 18px 18px}}
</style></head><body><div class="wrap">
<div class="hero"><h1>Brightspeed billing category mix, month over month</h1>
<p>Interactive view of the actual primary category assigned to every full-year billing call
({MONTH_RANGE}). {REFRESH} refresh: scored with the frozen 104-leaf taxonomy via local ML embedding (no LLM, no re-mining).</p>
<div class="kpis">
  <div class="kpi"><b>{total:,}</b><br>billing calls</div>
  <div class="kpi"><b>{len(months)}</b><br>months</div>
  <div class="kpi"><b>{n_cats}</b><br>macro categories</div>
  <div class="kpi"><b>{fallback:.1f}%</b><br>Other / fallback</div>
</div></div>
{divs_html}
<div class="note">Self-contained static HTML (Plotly offline). Source: {MONTH_RANGE} full-year tagged billing data, {REFRESH}.</div>
</div></body></html>"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    return out_path


# --------------------------------------------------------------------- subcategory
def _cat_color_map(cats: list[str]) -> dict[str, str]:
    return {c: CAT_PALETTE[i % len(CAT_PALETTE)] for i, c in enumerate(cats)}


def _sub_color_map(records: pd.DataFrame) -> dict[str, str]:
    keys = sorted(records["key"].unique())
    rng = np.random.RandomState(42)
    cols = [f"#{rng.randint(30, 240):02x}{rng.randint(30, 240):02x}{rng.randint(30, 240):02x}"
            for _ in keys]
    return dict(zip(keys, cols))


def write_subcategory_html(df: pd.DataFrame, months: list[str],
                           out_path: Path, total: int) -> Path:
    rec = monthly_subcategory(df)
    rec["key"] = rec["ai_category_1"] + "|||" + rec["ai_subcategory_1"]
    month_totals = {m: int(df[df.Call_Month == m].shape[0]) for m in months}
    categories = sorted(df["ai_category_1"].unique(),
                        key=lambda c: -df[df.ai_category_1 == c].shape[0])
    records = rec.rename(columns={
        "Call_Month": "month", "ai_category_1": "category",
        "ai_subcategory_1": "subcategory", "ai_tag_1": "canonical_tag"})[["month", "category", "subcategory", "canonical_tag", "calls"]].copy()

    cat_colors = _cat_color_map(categories)
    sub_colors = _sub_color_map(rec)

    data = {
        "months": months,
        "monthTotals": month_totals,
        "categories": categories,
        "records": records.to_dict("records"),
        "subColors": sub_colors,
        "catColors": cat_colors,
    }
    data_json = json.dumps(data, separators=(",", ":"))
    month_names_json = json.dumps({m: _month_label(m) for m in months},
                                  separators=(",", ":"))

    # build funnel figure for the "All" default se (used only for the placeholder div)
    funnel = build_sub_placeholder(months, total)
    trend = go.Figure()
    heat = go.Figure()

    fig_js = []
    fig_js.append(funnel)
    fig_js.append(trend)
    fig_js.append(heat)

    # We only embed plotly once; the custom script uses Plotly.react directly.
    div_funnel = _to_html(funnel, include_js=True)
    # strip the plotly script from subsequent placeholder figures (we render on load)
    div_trend = _to_html(trend, include_js=False)
    div_heat = _to_html(heat, include_js=False)

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Brightspeed MoM Subcategory Funnel</title>
<style>
body{{font-family:Arial,sans-serif;margin:0;background:#f6f7f8;color:#222}}
.wrap{{max-width:1500px;margin:0 auto;padding:28px}}
.card{{background:white;border-radius:12px;margin:18px 0;padding:8px 12px;box-shadow:0 1px 5px rgba(0,0,0,.08)}}
.hero{{background:white;padding:24px 30px;border-left:7px solid {BRAND};border-radius:12px}}
h1{{margin:0 0 8px;font-size:30px}} p{{margin:6px 0;color:#555}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap;margin-top:18px}}
.kpi{{background:#f3f0f6;border-radius:9px;padding:11px 16px;min-width:150px}}
.kpi b{{font-size:20px;color:{BRAND}}}
.controls{{background:white;padding:14px 22px;border-radius:12px;box-shadow:0 1px 5px rgba(0,0,0,.08);margin-top:18px}}
.controls label{{font-weight:bold;margin-right:10px;color:{BRAND}}}
#viewSelect{{padding:8px 12px;border-radius:6px;border:1px solid #ccc;font-size:14px}}
#metric{{font-weight:bold}}
.note{{font-size:12px;color:#777;padding:8px 18px 18px}}
</style></head><body><div class="wrap">
<div class="hero"><h1>Brightspeed billing subcategory mix, month over month</h1>
<p>Per-month subcategory doughnut funnels with a category filter ({MONTH_RANGE}). {REFRESH}
refresh: scored with the frozen 104-leaf taxonomy via local ML embedding (no LLM, no re-mining).</p>
<div class="kpis">
  <div class="kpi"><b>{total:,}</b><br>billing calls</div>
  <div class="kpi"><b>{len(months)}</b><br>months</div>
  <div class="kpi"><b>{len(categories)}</b><br>macro categories</div>
</div></div>
<div class="controls">
  <label for="viewSelect">View:</label>
  <select id="viewSelect">
    <option value="ALL">All billing</option>
    {"".join(f'<option value="{c}">{c}</option>' for c in categories)}
  </select>
  <span id="metric" style="margin-left:20px"></span>
</div>
<div class="card"><div id="funnel" style="height:1380px"></div></div>
<div class="card"><div id="trend" style="height:560px"></div></div>
<div class="card"><div id="heat" style="height:720px"></div></div>
<div class="note">Self-contained static HTML (Plotly offline). Source: {MONTH_RANGE} full-year tagged billing data, {REFRESH}.</div>
</div>
<div style="display:none">'dummy'</div>
<script type="text/javascript">
{_extract_plotly_div(div_funnel)}
</script>
<script type="text/javascript">
const D = {data_json};
const monthNames = {month_names_json};
function key(r){{return r.category + '|||' + r.subcategory}}
function fmt(n){{return n.toLocaleString('en-US')}}
function selectedRows(view){{return D.records.filter(r => view === 'ALL' || r.category === view)}}
function ytdRank(rows){{let m={{}}; rows.forEach(r => {{m[key(r)] = (m[key(r)] || 0) + r.calls}}); return Object.entries(m).sort((a,b) => b[1] - a[1])}}
function update(){{
  const view = document.getElementById('viewSelect').value;
  const rows = selectedRows(view);
  const ranks = ytdRank(rows);
  const selectedKeys = view === 'ALL' ? new Set(ranks.slice(0,18).map(x => x[0])) : new Set(ranks.map(x => x[0]));
  let monthPop = {{}}; D.months.forEach(m => monthPop[m] = rows.filter(r => r.month === m).reduce((a,b) => a + b.calls, 0));
  const maxPop = Math.max(...Object.values(monthPop));
  let traces = []; let annotations = [];
  D.months.forEach((m, idx) => {{
    const mr = rows.filter(r => r.month === m);
    let bucket = {{}}; let labels = {{}}; let colors = {{}};
    mr.forEach(r => {{ let k = key(r); let out = selectedKeys.has(k) ? k : '__REMAIN__';
      bucket[out] = (bucket[out] || 0) + r.calls;
      labels[out] = out === '__REMAIN__' ? 'Remaining subcategories' : r.subcategory;
      colors[out] = out === '__REMAIN__' ? '#D6DDE0' : (D.subColors[k] || '#ccc'); }});
    let entries = Object.entries(bucket).filter(x => x[1] > 0).sort((a,b) => b[1] - a[1]);
    let pop = monthPop[m], scale = Math.sqrt(pop / maxPop);
    let w = 0.22 + 0.42 * scale, x0 = .5 - w/2, x1 = .5 + w/2;
    let yTop = 0.985 - idx * 0.14, yBot = yTop - 0.115;
    traces.push({{type:'pie', labels: entries.map(e => labels[e[0]]), values: entries.map(e => e[1]),
      hole: .48, sort: false, direction: 'clockwise',
      marker: {{colors: entries.map(e => colors[e[0]]), line: {{color: '#fff', width: 1}}}},
      domain: {{x: [x0, x1], y: [yBot, yTop]}}, textinfo: 'none',
      hovertemplate: '<b>%{{label}}</b><br>Month: ' + monthNames[m] + '<br>Calls: %{{value:,}}<br>Share of selected month: %{{percent}}<extra></extra>',
      showlegend: false}});
    annotations.push({{x:.5, y:(yTop+yBot)/2, text:'<b>'+monthNames[m]+'</b><br>'+fmt(pop)+' calls', showarrow:false, font:{{size:14, color:'#243746'}}}});
  }});
  const total = Object.values(monthPop).reduce((a,b) => a + b, 0);
  document.getElementById('metric').innerHTML = '<b>' + (view === 'ALL' ? 'All billing' : view) + '</b><br>' + fmt(total) + ' YTD calls';
  Plotly.react('funnel', traces, {{title:{{text: view === 'ALL' ? 'Subcategory mix by month | all billing (' + {MONTH_RANGE_JS} + ')' : 'Subcategory mix by month | ' + view, x:.02, font:{{size:19}}}}, paper_bgcolor:'#fff', plot_bgcolor:'#fff', margin:{{l:20,r:20,t:55,b:15}}, annotations:annotations}}, {{responsive:true, displaylogo:false}});
  // trend top 10 leaves
  const topKeys = new Set(ranks.slice(0,10).map(x => x[0])); let trend = [];
  ranks.slice(0,10).forEach(([k, ytd]) => {{ let [cat, sub] = k.split('|||'); let yy = [], custom = [];
    D.months.forEach(m => {{ let rec = rows.find(r => r.month === m && key(r) === k); let n = rec ? rec.calls : 0;
      let p = monthPop[m] ? n / monthPop[m] : 0; yy.push(p); custom.push([n, fmt(n), monthPop[m]]); }});
    trend.push({{type:'scatter', mode:'lines+markers', name: sub, x: D.months.map(m => monthNames[m]), y: yy,
      customdata: custom, line:{{width:2.3, color: D.subColors[k] || '#333'}}, marker:{{size:7}},
      hovertemplate: '<b>'+sub+'</b><br>Month: %{{x}}<br>Calls: %{{customdata[1]}}<br>Share: %{{y:.2%}}<extra></extra>'}});
  }});
  Plotly.react('trend', trend, {{title:{{text:'MoM share trend | top 10 leaves in selected view', x:.02, font:{{size:18}}}},
    yaxis:{{tickformat:'.1%', title:'Share of selected monthly population'}}, xaxis:{{title:''}},
    legend:{{orientation:'h', y:-.2}}, margin:{{l:70,r:30,t:55,b:130}}, hovermode:'x unified',
    paper_bgcolor:'#fff', plot_bgcolor:'#fff'}}, {{responsive:true, displaylogo:false}});
  // heatmap top 25 leaves
  const hr = ranks.slice(0,25); let z = [], yt = [];
  hr.forEach(([k, v]) => {{ let [cat, sub] = k.split('|||'); yt.push(sub); let row = [];
    D.months.forEach(m => {{ let rec = rows.find(r => r.month === m && key(r) === k); let n = rec ? rec.calls : 0;
      row.push(monthPop[m] ? n / monthPop[m] : 0); }}); z.push(row); }});
  Plotly.react('heat', [{{type:'heatmap', x: D.months.map(m => monthNames[m]), y: yt, z: z,
    colorscale:[[0,'#f7f9fa'],[0.35,'#dceac7'],[1,'#7AC143']], colorbar:{{title:'Share', tickformat:'.1%'}},
    hovertemplate:'<b>%{{y}}</b><br>Month: %{{x}}<br>Share: %{{z:.2%}}<extra></extra>'}}],
    {{title:{{text:'Mix-shift heatmap | top 25 leaves', x:.02, font:{{size:18}}}},
      margin:{{l:310,r:70,t:55,b:50}}, paper_bgcolor:'#fff'}}, {{responsive:true, displaylogo:false}});
}}
document.getElementById('viewSelect').addEventListener('change', update);
update();
</script>
</body></html>"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    return out_path


def build_sub_placeholder(months: list[str], total: int) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(height=1380, paper_bgcolor="#fff")
    return fig


def _extract_plotly_div(div: str) -> str:
    """Return just the <script> ... </script> containing the embedded plotly.js.

    The subcategory placeholders are empty; we keep the full embedded library here.
    """
    start = div.find("<script")
    end = div.rfind("</script>")
    if start == -1 or end == -1:
        return ""
    return div[start:end + len("</script>")]


def write_counts_csv(df: pd.DataFrame, out_path: Path) -> Path:
    t = monthly_counts_csv(df)
    t.to_csv(out_path, index=False)
    return out_path


def build_all(parquet_path: Path, out_dir: Path | None = None) -> None:
    out_dir = Path(out_dir) if out_dir else OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"loading tagged parquet: {parquet_path}")
    df = load_tagged(parquet_path)
    months = _month_order(df)
    total = int(len(df))
    print(f"months: {months}  total calls: {total:,}")

    csv_path = write_counts_csv(df, out_dir / "brightspeed_mom_final_tagged_counts.csv")
    print("wrote", csv_path)

    cat_path = write_category_html(df, months, out_dir / "Brightspeed_MoM_Category_Pie_Funnel.html", total)
    print("wrote", cat_path, f"({cat_path.stat().st_size/1e6:.1f} MB)")

    sub_path = write_subcategory_html(df, months, out_dir / "Brightspeed_MoM_Subcategory_Pie_Funnel.html", total)
    print("wrote", sub_path, f"({sub_path.stat().st_size/1e6:.1f} MB)")
    print("MoM deliverables done.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parquet", type=Path, default=OUT / "billing_tagged_full.parquet")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    build_all(args.parquet, args.out)
