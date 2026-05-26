"""Insights & Summary — MBB-style consulting analytics with full drill-down controls.

Sections:
1. Executive summary KPIs
2. Profit Bridge — waterfall from Revenue → cost lines → Profit
3. Cost Pareto (80/20 view)
4. Trend focus chart (driven by sidebar dropdowns)
5. Revenue composition (donut + stacked area)
6. Cost structure (donut + top-N trend)
7. Profitability (profit bars + GM% trend)
8. MoM Profit Bridge — what drove last month's swing
9. Run-rate & Forecast — trailing-3M projection
10. Quarterly view + top/bottom tables
11. Cost efficiency — cost-to-revenue ratio trend
12. Scenario analysis — sensitivity sliders
13. Key insights callouts
14. Raw data + CSV
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import altair as alt
import pandas as pd
import streamlit as st

from pnl_reader import EXPENSE_KEYS, read_pnl
from theme import (
    ACCENT,
    ACCENT_DEEP,
    ACCENT_VIOLET,
    BG_PANEL,
    BORDER,
    DANGER,
    SUCCESS,
    TEXT_HI,
    TEXT_MID,
    TEXT_MUTED,
    WARN,
    brand_bar,
    fmt_chart_label,
    fmt_inr,
    fmt_pct,
    fmt_short_inr,
    inject_theme,
    kpi_tile,
    quote_banner,
    show_logo,
    sidebar_branding,
    t,
)
from year_analyzer import _fy_for_month

st.set_page_config(page_title="Insights · ABC", page_icon="📈", layout="wide")
inject_theme()
sidebar_branding()

from data_sources import require_master_or_stop
require_master_or_stop()


# ─── Header ─────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 5])
with col_logo:
    show_logo(width=120)
with col_title:
    st.title("5. INSIGHTS & SUMMARY")
    st.markdown(
        f'<div style="color:{TEXT_MUTED}; font-size:0.95rem; font-weight:500;">'
        "Consulting-grade analytics · drill-down · scenario testing"
        "</div>",
        unsafe_allow_html=True,
    )

quote_banner()


# ─── Load + build dataframe ─────────────────────────────────
@st.cache_data
def load_dataframe() -> pd.DataFrame:
    months = read_pnl()
    rows = []
    for m in months:
        rows.append({
            "month_dt": m.month,
            "month": m.label,
            "fy": _fy_for_month(m.month),
            "ultra_rev": m.ultra_rev,
            "premium_rev": m.premium_rev,
            "total_rev": m.total_rev,
            "salary": m.salary,
            "electricity": m.electricity,
            "repair": m.repair,
            "grocery": m.grocery,
            "mandir": m.mandir,
            "paytm": m.paytm,
            "misc": m.misc,
            "diesel": m.diesel,
            "total_exp": m.total_exp,
            "profit": m.profit,
            "gm_pct": m.gm_pct * 100,
        })
    return pd.DataFrame(rows)


try:
    df_all = load_dataframe()
except Exception as e:
    st.error(f"Could not load P&L data: {e}")
    st.stop()


# ─── Sidebar filters ────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔍 FILTERS")
    fy_options = sorted(df_all["fy"].unique().tolist(), reverse=True)
    selected_fy = st.selectbox("Fiscal Year", fy_options, key="ins_fy")

    df_fy = df_all[df_all["fy"] == selected_fy].sort_values("month_dt").reset_index(drop=True)
    month_labels = df_fy["month"].tolist()
    if len(month_labels) >= 2:
        range_idx = st.select_slider(
            "Month range",
            options=list(range(len(month_labels))),
            value=(0, len(month_labels) - 1),
            format_func=lambda i: month_labels[i],
        )
        df = df_fy.iloc[range_idx[0]:range_idx[1] + 1].copy()
    else:
        df = df_fy.copy()

    st.markdown("### 🎯 VIEW")
    segment = st.selectbox("Segment view", ["All", "Ultra only", "Premium only"], key="ins_seg")
    unit = st.selectbox("Display unit", ["₹ Lakhs", "₹ thousand", "₹"], key="ins_unit")
    time_grain = st.selectbox(
        "Time grouping",
        ["Monthly", "Quarterly", "Cumulative (YTD)"], key="ins_time_grain",
    )

    st.markdown("### 📊 TREND CHART")
    metric_focus = st.selectbox(
        "Metric focus",
        ["Revenue", "Profit", "Operating cost", "GM%"], key="ins_focus",
    )
    chart_type = st.selectbox("Chart type", ["Line", "Area", "Bar"], key="ins_chart_type")
    cmp_mode = st.radio(
        "Comparison overlay",
        ["None", "vs Avg (period)", "vs Prior month", "Trailing 3-mo MA"],
        key="ins_cmp",
    )

    st.markdown("### 🏷 DISPLAY")
    show_labels = st.checkbox("Show data labels on charts", value=True, key="ins_labels")
    cost_view = st.selectbox(
        "Cost view",
        ["Absolute (₹)", "% of revenue", "MoM growth %"], key="ins_cost_view",
    )

    st.markdown("### 🔮 FORECAST")
    forecast_horizon = st.selectbox("Forecast horizon (months)", [0, 1, 3, 6], key="ins_fc")

if segment == "Ultra only":
    df["rev_for_view"] = df["ultra_rev"]
elif segment == "Premium only":
    df["rev_for_view"] = df["premium_rev"]
else:
    df["rev_for_view"] = df["total_rev"]

if df.empty:
    st.warning("No data in selected range.")
    st.stop()


def scale(v: float) -> float:
    return v / {"₹ Lakhs": 1e5, "₹ thousand": 1e3, "₹": 1.0}[unit]


def fmt_unit(v: float) -> str:
    s = scale(v)
    if unit == "₹ Lakhs":
        return f"₹{s:.2f}L"
    if unit == "₹ thousand":
        return f"₹{s:,.1f}K"
    return f"₹{s:,.0f}"


# ─── KPI Row ────────────────────────────────────────────────
st.markdown("## EXECUTIVE SUMMARY")
total_rev = df["rev_for_view"].sum()
total_exp = df["total_exp"].sum()
total_profit = (df["rev_for_view"].sum() - df["total_exp"].sum()) if segment != "All" else df["profit"].sum()
avg_rev = df["rev_for_view"].mean()
avg_gm = (total_profit / (df["rev_for_view"].sum()) * 100) if df["rev_for_view"].sum() else 0
best_rev_row = df.loc[df["rev_for_view"].idxmax()]
worst_rev_row = df.loc[df["rev_for_view"].idxmin()]
spread = best_rev_row["rev_for_view"] - worst_rev_row["rev_for_view"]

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    kpi_tile(fmt_short_inr(total_rev), t("total_revenue"),
              actual=fmt_inr(total_rev),
              sub=f"{len(df)} months · {segment.lower()}", accent_color=ACCENT)
with k2:
    kpi_tile(fmt_short_inr(total_exp), t("operating_cost"),
              actual=fmt_inr(total_exp),
              sub=f"Avg {fmt_short_inr(total_exp/len(df))}/mo", accent_color=WARN)
with k3:
    kpi_tile(fmt_short_inr(total_profit), t("net_profit"),
              actual=fmt_inr(total_profit),
              sub=f"Avg {fmt_short_inr(total_profit/len(df))}/mo",
              accent_color=SUCCESS if total_profit >= 0 else DANGER)
with k4:
    kpi_tile(fmt_pct(avg_gm), t("gross_margin"),
              actual=f"Best {fmt_pct(df['gm_pct'].max())} · Worst {fmt_pct(df['gm_pct'].min())}",
              sub=f"Median {fmt_pct(df['gm_pct'].median())}", accent_color=ACCENT_VIOLET)
with k5:
    kpi_tile(fmt_short_inr(spread), "Best–Worst Spread",
              actual=fmt_inr(spread),
              sub=f"{best_rev_row['month']} → {worst_rev_row['month']}", accent_color=ACCENT_DEEP)


# ─── Chart helpers ──────────────────────────────────────────
def style_chart(c: alt.Chart, height: int = 280) -> alt.Chart:
    return (
        c.configure(background=BG_PANEL)
        .configure_view(stroke=BORDER, strokeWidth=1)
        .configure_axis(
            labelColor=TEXT_MID, titleColor=TEXT_MUTED, gridColor=BORDER,
            domainColor=BORDER, tickColor=BORDER, labelFontSize=11, titleFontSize=11,
        )
        .configure_legend(labelColor=TEXT_MID, titleColor=TEXT_MUTED)
        .configure_title(color=TEXT_HI, fontSize=14, anchor="start")
        .properties(height=height, background=BG_PANEL)
    )


def label_layer(data: pd.DataFrame, x_field: str, y_field: str, label_field: str,
                color: str = TEXT_HI, dy: int = -10, size: int = 10) -> alt.Chart:
    return (
        alt.Chart(data)
        .mark_text(align="center", baseline="bottom", dy=dy, fontSize=size,
                    fontWeight="bold", color=color)
        .encode(x=alt.X(x_field), y=alt.Y(y_field), text=alt.Text(f"{label_field}:N"))
    )


# ─── 1. PROFIT BRIDGE (Waterfall) ───────────────────────────
st.markdown("---")
st.markdown("## 1. PROFIT BRIDGE — REVENUE → COSTS → PROFIT")
st.caption("McKinsey-style cascade: how each cost line walks revenue down to profit "
            f"(period: {df.iloc[0]['month']} → {df.iloc[-1]['month']})")

bridge_rows = []
running = 0.0
bridge_rows.append({"label": "Revenue", "start": 0, "end": total_rev,
                     "delta": total_rev, "kind": "Revenue"})
running = total_rev
exp_breakdown = sorted(
    [(k.title(), -df[k].sum()) for k in EXPENSE_KEYS if df[k].sum() > 0],
    key=lambda x: x[1],  # most negative first (biggest costs first)
)
for label, delta in exp_breakdown:
    bridge_rows.append({"label": label, "start": running + delta, "end": running,
                         "delta": delta, "kind": "Cost"})
    running = running + delta
bridge_rows.append({"label": "Net Profit", "start": 0, "end": running,
                     "delta": running, "kind": "Total"})

bridge = pd.DataFrame(bridge_rows)
bridge["start_s"] = bridge["start"].apply(scale)
bridge["end_s"] = bridge["end"].apply(scale)
bridge["delta_s"] = bridge["delta"].apply(scale)
bridge["label_text"] = bridge["delta"].apply(fmt_chart_label)
bridge["order"] = list(range(len(bridge)))

color_scale = alt.Scale(domain=["Revenue", "Cost", "Total"],
                          range=[ACCENT, WARN, SUCCESS if running >= 0 else DANGER])

bars = (
    alt.Chart(bridge)
    .mark_bar(size=35)
    .encode(
        x=alt.X("label:N", sort=bridge["label"].tolist(), title=None,
                axis=alt.Axis(labelAngle=-25)),
        y=alt.Y("start_s:Q", title=f"₹ ({unit})"),
        y2="end_s:Q",
        color=alt.Color("kind:N", scale=color_scale, legend=alt.Legend(orient="top", title=None)),
        tooltip=["label", "kind", alt.Tooltip("delta:Q", format=",.0f")],
    )
)

if show_labels:
    bridge["text_y"] = bridge.apply(
        lambda r: max(r["start_s"], r["end_s"]) + abs(r["delta_s"]) * 0.04, axis=1,
    )
    text = (
        alt.Chart(bridge)
        .mark_text(align="center", baseline="bottom", dy=-2, fontSize=10,
                    fontWeight="bold", color=TEXT_HI)
        .encode(
            x=alt.X("label:N", sort=bridge["label"].tolist()),
            y="text_y:Q",
            text=alt.Text("label_text:N"),
        )
    )
    bridge_chart = bars + text
else:
    bridge_chart = bars

st.altair_chart(style_chart(bridge_chart, 360), use_container_width=True)
st.caption(f"💡 **Insight**: Every ₹100 of revenue is consumed by ₹{(total_exp/total_rev*100):.0f} "
            f"in operating costs, leaving ₹{(total_profit/total_rev*100):.0f} as profit. "
            f"Biggest cost line: **{exp_breakdown[0][0]}** ({fmt_short_inr(-exp_breakdown[0][1])}, "
            f"{(-exp_breakdown[0][1]/total_exp*100):.0f}% of total opex).")


# ─── 2. COST PARETO (80/20) ─────────────────────────────────
st.markdown("---")
st.markdown("## 2. COST PARETO — WHERE THE MONEY GOES")
st.caption("Sorted-descending bars + cumulative % line. Look for the 80/20 break.")

pareto = pd.DataFrame({
    "category": [k.title() for k in EXPENSE_KEYS],
    "amount": [df[k].sum() for k in EXPENSE_KEYS],
})
pareto = pareto[pareto["amount"] > 0].sort_values("amount", ascending=False).reset_index(drop=True)
pareto["pct"] = pareto["amount"] / pareto["amount"].sum() * 100
pareto["cum_pct"] = pareto["pct"].cumsum()
pareto["amount_s"] = pareto["amount"].apply(scale)
pareto["label_text"] = pareto["amount"].apply(fmt_chart_label)
pareto["cum_label"] = pareto["cum_pct"].apply(lambda v: f"{v:.0f}%")

bars = (
    alt.Chart(pareto)
    .mark_bar(color=ACCENT, cornerRadiusEnd=3)
    .encode(
        x=alt.X("category:N", sort=pareto["category"].tolist(), title=None,
                axis=alt.Axis(labelAngle=-30)),
        y=alt.Y("amount_s:Q", title=f"Amount ({unit})"),
        tooltip=["category", alt.Tooltip("amount:Q", format=",.0f"),
                 alt.Tooltip("pct:Q", format=".1f"),
                 alt.Tooltip("cum_pct:Q", format=".1f")],
    )
)
line = (
    alt.Chart(pareto)
    .mark_line(color=DANGER, strokeWidth=2.5, point=alt.OverlayMarkDef(filled=True, size=60))
    .encode(
        x=alt.X("category:N", sort=pareto["category"].tolist()),
        y=alt.Y("cum_pct:Q", axis=alt.Axis(title="Cumulative %", titleColor=DANGER,
                                              labelColor=DANGER)),
    )
)
layers = [bars, line]
if show_labels:
    bar_text = (
        alt.Chart(pareto)
        .mark_text(align="center", baseline="bottom", dy=-6, fontSize=12,
                    fontWeight="bold", color=TEXT_HI)
        .encode(x=alt.X("category:N", sort=pareto["category"].tolist()),
                 y="amount_s:Q", text="label_text:N")
    )
    # Place cumulative % labels to the right of each point so they don't collide
    cum_text = (
        alt.Chart(pareto)
        .mark_text(align="left", baseline="middle", dx=8, dy=-2, fontSize=11,
                    fontWeight="bold", color=DANGER)
        .encode(x=alt.X("category:N", sort=pareto["category"].tolist()),
                 y=alt.Y("cum_pct:Q"), text="cum_label:N")
    )
    layers.extend([bar_text, cum_text])

pareto_chart = alt.layer(*layers).resolve_scale(y="independent")
st.altair_chart(style_chart(pareto_chart, 380), use_container_width=True)

eighty_idx = pareto["cum_pct"].searchsorted(80) + 1
top_drivers = pareto.head(eighty_idx)["category"].tolist()
st.caption(f"💡 **Insight**: **{len(top_drivers)} of {len(pareto)} categories** drive 80% of cost "
            f"→ {', '.join(top_drivers)}. Focus cost-control efforts here.")


# ─── 3. Focus chart (Trend) ─────────────────────────────────
METRIC_MAP = {
    "Revenue":        ("rev_for_view", ACCENT,         "Revenue"),
    "Profit":         ("profit",       SUCCESS,        "Profit"),
    "Operating cost": ("total_exp",    WARN,           "Operating cost"),
    "GM%":            ("gm_pct",       ACCENT_VIOLET,  "Gross Margin (%)"),
}

st.markdown("---")
st.markdown(f"## 3. {metric_focus.upper()} TREND")
st.caption(f"Time grouping: **{time_grain}** · Chart: **{chart_type}** · Overlay: **{cmp_mode}**")

col, color, axis_title = METRIC_MAP[metric_focus]


# Build df_view based on time_grain
def quarter_for(dt) -> str:
    m = dt.month
    if m in (4, 5, 6): return "Q1"
    if m in (7, 8, 9): return "Q2"
    if m in (10, 11, 12): return "Q3"
    return "Q4"


if time_grain == "Quarterly":
    df_view = df.copy()
    df_view["bucket"] = df_view["month_dt"].apply(quarter_for)
    agg = {col: "sum"}
    if col == "gm_pct":
        # recompute GM% from rev/exp for quarter
        df_view = df_view.groupby("bucket").agg(
            total_rev=("total_rev", "sum"), total_exp=("total_exp", "sum"),
            profit=("profit", "sum"), rev_for_view=("rev_for_view", "sum"),
        ).reset_index()
        df_view["gm_pct"] = df_view.apply(
            lambda r: (r["profit"] / r["total_rev"] * 100) if r["total_rev"] else 0, axis=1,
        )
        df_view["bucket_label"] = df_view["bucket"]
    else:
        df_view = df_view.groupby("bucket").agg(**{col: (col, "sum")}).reset_index()
        df_view["bucket_label"] = df_view["bucket"]
elif time_grain == "Cumulative (YTD)":
    df_view = df.copy().reset_index(drop=True)
    if col != "gm_pct":
        df_view[col] = df_view[col].cumsum()
    df_view["bucket_label"] = df_view["month"]
else:
    df_view = df.copy().reset_index(drop=True)
    df_view["bucket_label"] = df_view["month"]

df_view["value_scaled"] = (df_view[col].apply(scale) if metric_focus != "GM%"
                              else df_view[col])
df_view["value_label"] = df_view[col].apply(
    lambda v: f"{v:.1f}%" if metric_focus == "GM%" else fmt_chart_label(v)
)
y_title = axis_title if metric_focus == "GM%" else f"{axis_title} ({unit})"

sort_order = df_view["bucket_label"].tolist()
if chart_type == "Line":
    base = alt.Chart(df_view).mark_line(
        point=alt.OverlayMarkDef(filled=True, size=70), strokeWidth=2.8, color=color,
    )
elif chart_type == "Area":
    base = alt.Chart(df_view).mark_area(opacity=0.45, line={"strokeWidth": 2.5}, color=color)
else:
    base = alt.Chart(df_view).mark_bar(cornerRadiusEnd=3, color=color)

main = base.encode(
    x=alt.X("bucket_label:N", sort=sort_order, title=None,
            axis=alt.Axis(labelAngle=-30)),
    y=alt.Y("value_scaled:Q", title=y_title),
    tooltip=["bucket_label", alt.Tooltip("value_scaled:Q", format=",.2f")],
)

layers = [main]
if cmp_mode == "vs Avg (period)":
    avg_val = df_view["value_scaled"].mean()
    layers.append(alt.Chart(pd.DataFrame({"y": [avg_val]})).mark_rule(
        color=WARN, strokeDash=[6, 4], strokeWidth=1.5).encode(y="y:Q"))
elif cmp_mode == "vs Prior month":
    df_view2 = df_view.copy()
    df_view2["value_prev"] = df_view2["value_scaled"].shift(1)
    layers.append(alt.Chart(df_view2).mark_line(
        strokeDash=[5, 4], strokeWidth=1.6, color=TEXT_MUTED, point=False,
    ).encode(
        x=alt.X("bucket_label:N", sort=sort_order), y="value_prev:Q",
    ))
elif cmp_mode == "Trailing 3-mo MA":
    df_view2 = df_view.copy()
    df_view2["ma3"] = df_view2["value_scaled"].rolling(3, min_periods=1).mean()
    layers.append(alt.Chart(df_view2).mark_line(
        strokeDash=[4, 3], strokeWidth=1.8, color=ACCENT_VIOLET,
    ).encode(
        x=alt.X("bucket_label:N", sort=sort_order), y="ma3:Q",
    ))

if show_labels:
    layers.append(
        alt.Chart(df_view).mark_text(
            align="center", baseline="bottom", dy=-9, fontSize=12,
            fontWeight="bold", color=TEXT_HI,
        ).encode(
            x=alt.X("bucket_label:N", sort=sort_order),
            y=alt.Y("value_scaled:Q"),
            text="value_label:N",
        )
    )

st.altair_chart(style_chart(alt.layer(*layers), 380), use_container_width=True)


# ─── 4. Revenue composition ─────────────────────────────────
st.markdown("---")
st.markdown("## 4. REVENUE COMPOSITION")
c1, c2 = st.columns([2, 3])

with c1:
    comp = pd.DataFrame({
        "segment": ["Ultra", "Premium"],
        "amount": [df["ultra_rev"].sum(), df["premium_rev"].sum()],
    })
    comp["pct"] = comp["amount"] / comp["amount"].sum() * 100
    comp["pct_label"] = comp["pct"].apply(lambda v: f"{v:.0f}%")
    donut = (
        alt.Chart(comp)
        .mark_arc(innerRadius=85, outerRadius=160, stroke=BG_PANEL, strokeWidth=3)
        .encode(
            theta="amount:Q",
            color=alt.Color("segment:N",
                             scale=alt.Scale(domain=["Ultra", "Premium"],
                                              range=[ACCENT, ACCENT_VIOLET]),
                             legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["segment", alt.Tooltip("amount:Q", format=",.0f"),
                     alt.Tooltip("pct:Q", format=".1f")],
        )
        .properties(title=f"Mix · total {fmt_short_inr(comp['amount'].sum())}")
    )
    if show_labels:
        inside = (
            alt.Chart(comp).mark_text(
                radius=125, fontSize=14, fontWeight="bold", color=TEXT_HI,
            ).encode(
                theta=alt.Theta("amount:Q", stack=True),
                text="pct_label:N",
            )
        )
        donut = donut + inside
    st.altair_chart(style_chart(donut, 400), use_container_width=True)

with c2:
    rev_long = df.melt(id_vars=["month", "month_dt"],
                        value_vars=["ultra_rev", "premium_rev"],
                        var_name="segment", value_name="amount")
    rev_long["segment"] = rev_long["segment"].map({"ultra_rev": "Ultra",
                                                      "premium_rev": "Premium"})
    rev_long["amount_scaled"] = rev_long["amount"].apply(scale)
    chart = (
        alt.Chart(rev_long)
        .mark_area(opacity=0.85, line={"strokeWidth": 2.5})
        .encode(
            x=alt.X("month:N", sort=df["month"].tolist(), title=None,
                    axis=alt.Axis(labelAngle=-30)),
            y=alt.Y("amount_scaled:Q", title=f"Revenue ({unit})", stack="zero"),
            color=alt.Color("segment:N",
                             scale=alt.Scale(domain=["Ultra", "Premium"],
                                              range=[ACCENT, ACCENT_VIOLET]),
                             legend=alt.Legend(orient="top", title=None)),
            tooltip=["month", "segment", alt.Tooltip("amount:Q", format=",.0f")],
        )
        .properties(title="Monthly revenue — Ultra + Premium stacked")
    )

    if show_labels:
        # Totals per month for label position
        totals = df.copy()
        totals["total_scaled"] = totals["total_rev"].apply(scale)
        totals["label_text"] = totals["total_rev"].apply(fmt_chart_label)
        chart = chart + (
            alt.Chart(totals).mark_text(
                align="center", baseline="bottom", dy=-4, fontSize=9.5,
                fontWeight="bold", color=TEXT_HI,
            ).encode(
                x=alt.X("month:N", sort=df["month"].tolist()),
                y="total_scaled:Q", text="label_text:N",
            )
        )
    st.altair_chart(style_chart(chart, 300), use_container_width=True)


# ─── 5. Cost structure ──────────────────────────────────────
st.markdown("---")
st.markdown("## 5. COST STRUCTURE")
c1, c2 = st.columns([2, 3])

with c1:
    exp_totals = pd.DataFrame({
        "category": [k.title() for k in EXPENSE_KEYS],
        "amount": [df[k].sum() for k in EXPENSE_KEYS],
    })
    exp_totals = exp_totals[exp_totals["amount"] > 0].sort_values("amount", ascending=False)
    exp_totals["pct"] = exp_totals["amount"] / exp_totals["amount"].sum() * 100

    exp_palette = [ACCENT, ACCENT_VIOLET, SUCCESS, WARN, DANGER, "#0284C7", "#7C3AED", TEXT_MUTED]
    exp_totals["pct_label"] = exp_totals["pct"].apply(
        lambda v: f"{v:.0f}%" if v >= 4 else "",
    )
    donut = (
        alt.Chart(exp_totals)
        .mark_arc(innerRadius=75, outerRadius=160, stroke=BG_PANEL, strokeWidth=3)
        .encode(
            theta="amount:Q",
            color=alt.Color("category:N",
                             scale=alt.Scale(range=exp_palette),
                             legend=alt.Legend(orient="bottom", title=None, columns=2)),
            tooltip=["category", alt.Tooltip("amount:Q", format=",.0f"),
                     alt.Tooltip("pct:Q", format=".1f")],
        )
        .properties(title="Expense composition")
    )
    if show_labels:
        inside = (
            alt.Chart(exp_totals).mark_text(
                radius=120, fontSize=13, fontWeight="bold", color=TEXT_HI,
            ).encode(
                theta=alt.Theta("amount:Q", stack=True),
                text="pct_label:N",
            )
        )
        donut = donut + inside
    st.altair_chart(style_chart(donut, 400), use_container_width=True)

with c2:
    top_n = st.selectbox("How many top expense categories to trend?",
                          [3, 4, 5, 6, 8], index=0, key="ins_top_n")
    top_cats = exp_totals.head(top_n)["category"].str.lower().tolist()
    if top_cats:
        cat_long = df.melt(id_vars=["month", "month_dt"], value_vars=top_cats,
                            var_name="category", value_name="amount")
        cat_long["category"] = cat_long["category"].str.title()

        # Apply cost_view transformation
        if cost_view == "% of revenue":
            month_rev = df.set_index("month")["total_rev"]
            cat_long["amount"] = cat_long.apply(
                lambda r: (r["amount"] / month_rev[r["month"]] * 100)
                if month_rev[r["month"]] else 0, axis=1,
            )
            y_axis_title = "% of monthly revenue"
            cat_long["amount_scaled"] = cat_long["amount"]
            cat_long["label_text"] = cat_long["amount"].apply(lambda v: f"{v:.0f}%")
        elif cost_view == "MoM growth %":
            cat_long = cat_long.sort_values(["category", "month_dt"])
            cat_long["amount"] = cat_long.groupby("category")["amount"].pct_change() * 100
            cat_long["amount_scaled"] = cat_long["amount"]
            cat_long["label_text"] = cat_long["amount"].apply(
                lambda v: f"{v:+.0f}%" if pd.notna(v) else "")
            y_axis_title = "MoM growth (%)"
        else:
            cat_long["amount_scaled"] = cat_long["amount"].apply(scale)
            cat_long["label_text"] = cat_long["amount"].apply(fmt_chart_label)
            y_axis_title = f"Amount ({unit})"

        chart = (
            alt.Chart(cat_long)
            .mark_line(point=alt.OverlayMarkDef(filled=True, size=60), strokeWidth=2.5)
            .encode(
                x=alt.X("month:N", sort=df["month"].tolist(), title=None,
                        axis=alt.Axis(labelAngle=-30)),
                y=alt.Y("amount_scaled:Q", title=y_axis_title),
                color=alt.Color("category:N",
                                 scale=alt.Scale(range=exp_palette[:top_n]),
                                 legend=alt.Legend(orient="top", title=None)),
                tooltip=["month", "category", alt.Tooltip("amount:Q", format=",.2f")],
            )
            .properties(title=f"Top-{top_n} expense categories · {cost_view.lower()}")
        )
        if show_labels:
            chart = chart + (
                alt.Chart(cat_long).mark_text(
                    align="center", baseline="bottom", dy=-6, fontSize=9,
                    fontWeight="bold",
                ).encode(
                    x=alt.X("month:N", sort=df["month"].tolist()),
                    y="amount_scaled:Q", text="label_text:N",
                    color=alt.Color("category:N",
                                     scale=alt.Scale(range=exp_palette[:top_n]),
                                     legend=None),
                )
            )
        st.altair_chart(style_chart(chart, 340), use_container_width=True)


# ─── 6. Profitability ───────────────────────────────────────
st.markdown("---")
st.markdown("## 6. PROFITABILITY")
c1, c2 = st.columns([3, 2])

with c1:
    df_p = df.copy()
    df_p["profit_scaled"] = df_p["profit"].apply(scale)
    df_p["state"] = df_p["profit"].apply(lambda v: "Loss" if v < 0 else "Profit")
    df_p["label_text"] = df_p["profit"].apply(fmt_chart_label)
    bars = (
        alt.Chart(df_p)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=alt.X("month:N", sort=df["month"].tolist(), title=None,
                    axis=alt.Axis(labelAngle=-30)),
            y=alt.Y("profit_scaled:Q", title=f"Profit ({unit})"),
            color=alt.Color("state:N",
                             scale=alt.Scale(domain=["Profit", "Loss"],
                                              range=[SUCCESS, DANGER]),
                             legend=alt.Legend(orient="top", title=None)),
            tooltip=["month", alt.Tooltip("profit:Q", format=",.0f"),
                     alt.Tooltip("gm_pct:Q", format=".1f")],
        )
        .properties(title="Monthly profit / loss")
    )
    if show_labels:
        pos = df_p[df_p["profit"] >= 0]
        neg = df_p[df_p["profit"] < 0]
        pos_layer = alt.Chart(pos).mark_text(
            align="center", baseline="bottom", dy=-4, fontSize=10,
            fontWeight="bold", color=TEXT_HI,
        ).encode(
            x=alt.X("month:N", sort=df["month"].tolist()),
            y="profit_scaled:Q", text="label_text:N",
        )
        neg_layer = alt.Chart(neg).mark_text(
            align="center", baseline="top", dy=4, fontSize=10,
            fontWeight="bold", color=TEXT_HI,
        ).encode(
            x=alt.X("month:N", sort=df["month"].tolist()),
            y="profit_scaled:Q", text="label_text:N",
        )
        bars = bars + pos_layer + neg_layer
    st.altair_chart(style_chart(bars, 310), use_container_width=True)

with c2:
    df_g = df.copy()
    df_g["label_text"] = df_g["gm_pct"].apply(lambda v: f"{v:.1f}%")
    avg_g = df_g["gm_pct"].mean()
    line = (
        alt.Chart(df_g)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=70),
                    strokeWidth=2.8, color=ACCENT_VIOLET)
        .encode(
            x=alt.X("month:N", sort=df["month"].tolist(), title=None,
                    axis=alt.Axis(labelAngle=-30)),
            y=alt.Y("gm_pct:Q", title="Gross Margin (%)"),
            tooltip=["month", alt.Tooltip("gm_pct:Q", format=".1f")],
        )
    )
    rule = alt.Chart(pd.DataFrame({"y": [avg_g]})).mark_rule(
        color=WARN, strokeDash=[6, 4], strokeWidth=1.5,
    ).encode(y="y:Q")
    chart = line + rule
    if show_labels:
        chart = chart + (
            alt.Chart(df_g).mark_text(
                align="center", baseline="bottom", dy=-8, fontSize=10,
                fontWeight="bold", color=ACCENT_DEEP,
            ).encode(
                x=alt.X("month:N", sort=df["month"].tolist()),
                y="gm_pct:Q", text="label_text:N",
            )
        )
    st.altair_chart(style_chart(chart.properties(title=f"GM% trend · avg {avg_g:.1f}%"), 310),
                     use_container_width=True)


# ─── 7. MoM PROFIT BRIDGE ───────────────────────────────────
if len(df) >= 2:
    st.markdown("---")
    st.markdown("## 7. MoM PROFIT BRIDGE — WHAT DROVE LAST MONTH'S SWING")
    cur = df.iloc[-1]
    prev = df.iloc[-2]
    rev_change = cur["total_rev"] - prev["total_rev"]
    exp_change = -(cur["total_exp"] - prev["total_exp"])  # negative cost increase = profit drag
    profit_check = rev_change + exp_change  # should equal cur.profit - prev.profit

    mom_rows = [
        {"label": f"{prev['month']} Profit", "start": 0, "end": prev["profit"],
         "delta": prev["profit"], "kind": "Anchor"},
        {"label": "Revenue Δ", "start": prev["profit"],
         "end": prev["profit"] + rev_change, "delta": rev_change,
         "kind": "Positive" if rev_change >= 0 else "Negative"},
        {"label": "Cost Δ", "start": prev["profit"] + rev_change,
         "end": prev["profit"] + rev_change + exp_change, "delta": exp_change,
         "kind": "Positive" if exp_change >= 0 else "Negative"},
        {"label": f"{cur['month']} Profit", "start": 0, "end": cur["profit"],
         "delta": cur["profit"], "kind": "Anchor"},
    ]
    mom = pd.DataFrame(mom_rows)
    mom["start_s"] = mom["start"].apply(scale)
    mom["end_s"] = mom["end"].apply(scale)
    mom["delta_s"] = mom["delta"].apply(scale)
    mom["label_text"] = mom["delta"].apply(
        lambda v: ("+" if v >= 0 else "") + fmt_chart_label(v),
    )
    mom_scale = alt.Scale(
        domain=["Anchor", "Positive", "Negative"],
        range=[ACCENT_DEEP, SUCCESS, DANGER],
    )
    mom_bars = (
        alt.Chart(mom)
        .mark_bar(size=55)
        .encode(
            x=alt.X("label:N", sort=mom["label"].tolist(), title=None,
                    axis=alt.Axis(labelAngle=-15)),
            y=alt.Y("start_s:Q", title=f"Profit ({unit})"),
            y2="end_s:Q",
            color=alt.Color("kind:N", scale=mom_scale, legend=alt.Legend(orient="top", title=None)),
            tooltip=["label", alt.Tooltip("delta:Q", format=",.0f")],
        )
    )
    if show_labels:
        mom["text_y"] = mom.apply(
            lambda r: max(r["start_s"], r["end_s"]) + abs(r["delta_s"]) * 0.06, axis=1,
        )
        mom_bars = mom_bars + (
            alt.Chart(mom).mark_text(
                align="center", baseline="bottom", dy=-2, fontSize=11,
                fontWeight="bold", color=TEXT_HI,
            ).encode(
                x=alt.X("label:N", sort=mom["label"].tolist()),
                y="text_y:Q", text="label_text:N",
            )
        )
    st.altair_chart(style_chart(mom_bars, 300), use_container_width=True)

    if rev_change >= 0 and exp_change >= 0:
        verdict = f"Both **revenue grew** ({fmt_short_inr(rev_change)}) AND **costs fell** ({fmt_short_inr(-exp_change)}) — clean win."
    elif rev_change >= 0 and exp_change < 0:
        verdict = f"Revenue up {fmt_short_inr(rev_change)} but **costs rose** by {fmt_short_inr(-exp_change)} — partial gain."
    elif rev_change < 0 and exp_change >= 0:
        verdict = f"Revenue dropped {fmt_short_inr(-rev_change)} but **cost discipline saved** {fmt_short_inr(exp_change)}."
    else:
        verdict = f"Double trouble — revenue down {fmt_short_inr(-rev_change)}, costs up {fmt_short_inr(-exp_change)}. Investigate."
    st.caption(f"💡 **Insight**: {verdict}")


# ─── 8. RUN-RATE & FORECAST ─────────────────────────────────
st.markdown("---")
st.markdown("## 8. RUN-RATE & FORECAST")
st.caption(f"Trailing 3-month average projected forward {forecast_horizon} months.")

run_df = df.copy().sort_values("month_dt").reset_index(drop=True)
run_df["rev_scaled"] = run_df["total_rev"].apply(scale)
run_df["kind"] = "Actual"

if forecast_horizon > 0 and len(run_df) >= 3:
    trail_avg = run_df["total_rev"].tail(3).mean()
    last_dt = run_df.iloc[-1]["month_dt"]
    fc_rows = []
    for i in range(1, forecast_horizon + 1):
        new_dt = (last_dt + pd.DateOffset(months=i)).to_pydatetime()
        fc_rows.append({
            "month_dt": new_dt,
            "month": new_dt.strftime("%b %Y"),
            "total_rev": trail_avg,
            "rev_scaled": scale(trail_avg),
            "kind": "Forecast",
        })
    fc_df = pd.DataFrame(fc_rows)
    plot_df = pd.concat([run_df[["month_dt", "month", "total_rev", "rev_scaled", "kind"]],
                          fc_df], ignore_index=True)
else:
    plot_df = run_df[["month_dt", "month", "total_rev", "rev_scaled", "kind"]]

plot_df["label_text"] = plot_df["total_rev"].apply(fmt_chart_label)
sort_run = plot_df["month"].tolist()

base = (
    alt.Chart(plot_df).mark_line(point=alt.OverlayMarkDef(filled=True, size=70), strokeWidth=2.8)
    .encode(
        x=alt.X("month:N", sort=sort_run, title=None, axis=alt.Axis(labelAngle=-30)),
        y=alt.Y("rev_scaled:Q", title=f"Revenue ({unit})"),
        color=alt.Color("kind:N",
                         scale=alt.Scale(domain=["Actual", "Forecast"],
                                          range=[ACCENT, ACCENT_VIOLET]),
                         legend=alt.Legend(orient="top", title=None)),
        strokeDash=alt.condition(alt.datum.kind == "Forecast",
                                   alt.value([5, 4]), alt.value([1, 0])),
        tooltip=["month", "kind", alt.Tooltip("total_rev:Q", format=",.0f")],
    )
)
layers = [base]
if show_labels:
    layers.append(
        alt.Chart(plot_df).mark_text(
            align="center", baseline="bottom", dy=-8, fontSize=10,
            fontWeight="bold", color=TEXT_HI,
        ).encode(
            x=alt.X("month:N", sort=sort_run), y="rev_scaled:Q", text="label_text:N",
        )
    )
st.altair_chart(style_chart(alt.layer(*layers), 300), use_container_width=True)

if forecast_horizon > 0 and len(run_df) >= 3:
    proj_annual = trail_avg * 12
    st.caption(f"💡 **Run-rate**: At current trailing-3M pace, annualized revenue would be "
                f"**{fmt_short_inr(proj_annual)}** "
                f"vs FY actual so far of **{fmt_short_inr(total_rev)}**.")


# ─── 9. QUARTERLY VIEW + TOP/BOTTOM ─────────────────────────
st.markdown("---")
st.markdown("## 9. QUARTERLY VIEW")
c1, c2 = st.columns([3, 2])

df_q = df.copy()
df_q["quarter"] = df_q["month_dt"].apply(quarter_for)
agg = df_q.groupby("quarter").agg(
    revenue=("total_rev", "sum"),
    expenses=("total_exp", "sum"),
    profit=("profit", "sum"),
).reset_index()
agg["order"] = agg["quarter"].map({"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4})
agg = agg.sort_values("order")
agg_long = agg.melt(id_vars=["quarter"], value_vars=["revenue", "expenses", "profit"],
                    var_name="metric", value_name="amount")
agg_long["amount_scaled"] = agg_long["amount"].apply(scale)
agg_long["metric"] = agg_long["metric"].str.title()
agg_long["label_text"] = agg_long["amount"].apply(fmt_chart_label)

with c1:
    bars = (
        alt.Chart(agg_long)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=alt.X("quarter:N", title=None, sort=["Q1", "Q2", "Q3", "Q4"],
                    axis=alt.Axis(labelAngle=0)),
            xOffset=alt.XOffset("metric:N", sort=["Revenue", "Expenses", "Profit"]),
            y=alt.Y("amount_scaled:Q", title=f"Amount ({unit})"),
            color=alt.Color("metric:N",
                             scale=alt.Scale(domain=["Revenue", "Expenses", "Profit"],
                                              range=[ACCENT, WARN, SUCCESS]),
                             legend=alt.Legend(orient="top", title=None)),
            tooltip=["quarter", "metric", alt.Tooltip("amount:Q", format=",.0f")],
        )
    )
    layers = [bars]
    if show_labels:
        layers.append(
            alt.Chart(agg_long).mark_text(
                align="center", baseline="bottom", dy=-4, fontSize=11,
                fontWeight="bold", color=TEXT_HI,
            ).encode(
                x=alt.X("quarter:N", sort=["Q1", "Q2", "Q3", "Q4"]),
                xOffset=alt.XOffset("metric:N", sort=["Revenue", "Expenses", "Profit"]),
                y="amount_scaled:Q", text="label_text:N",
            )
        )
    chart = alt.layer(*layers).properties(
        title="Revenue · Expenses · Profit by quarter",
    )
    st.altair_chart(style_chart(chart, 320), use_container_width=True)

with c2:
    rank_n = st.selectbox("Top / bottom how many months?", [3, 5, 7], index=0, key="ins_rank_n")
    st.markdown(f"##### TOP-{rank_n} MONTHS — PROFIT")
    top = df.nlargest(rank_n, "profit")[["month", "total_rev", "profit", "gm_pct"]].copy()
    top["Revenue"] = top["total_rev"].apply(fmt_unit)
    top["Profit"] = top["profit"].apply(fmt_unit)
    top["GM%"] = top["gm_pct"].apply(lambda v: f"{v:.1f}%")
    st.dataframe(
        top[["month", "Revenue", "Profit", "GM%"]].rename(columns={"month": "Month"}),
        use_container_width=True, hide_index=True,
    )
    st.markdown(f"##### BOTTOM-{rank_n} MONTHS — PROFIT")
    bot = df.nsmallest(rank_n, "profit")[["month", "total_rev", "profit", "gm_pct"]].copy()
    bot["Revenue"] = bot["total_rev"].apply(fmt_unit)
    bot["Profit"] = bot["profit"].apply(fmt_unit)
    bot["GM%"] = bot["gm_pct"].apply(lambda v: f"{v:.1f}%")
    st.dataframe(
        bot[["month", "Revenue", "Profit", "GM%"]].rename(columns={"month": "Month"}),
        use_container_width=True, hide_index=True,
    )


# ─── 10. COST EFFICIENCY ─────────────────────────────────────
st.markdown("---")
st.markdown("## 10. COST EFFICIENCY — COST/REVENUE RATIO")
st.caption("Lower = more efficient. Watch the trend slope, not just the level.")

eff = df.copy()
eff["cost_to_rev"] = eff["total_exp"] / eff["total_rev"] * 100
eff["label_text"] = eff["cost_to_rev"].apply(lambda v: f"{v:.0f}%")

eff_line = (
    alt.Chart(eff).mark_line(
        point=alt.OverlayMarkDef(filled=True, size=70), strokeWidth=2.8, color=WARN,
    ).encode(
        x=alt.X("month:N", sort=df["month"].tolist(), title=None,
                axis=alt.Axis(labelAngle=-30)),
        y=alt.Y("cost_to_rev:Q", title="Cost / Revenue (%)"),
        tooltip=["month", alt.Tooltip("cost_to_rev:Q", format=".1f")],
    )
)
avg_eff = eff["cost_to_rev"].mean()
eff_rule = alt.Chart(pd.DataFrame({"y": [avg_eff]})).mark_rule(
    color=TEXT_MUTED, strokeDash=[6, 4], strokeWidth=1.5,
).encode(y="y:Q")
eff_chart = eff_line + eff_rule
if show_labels:
    eff_chart = eff_chart + (
        alt.Chart(eff).mark_text(
            align="center", baseline="bottom", dy=-8, fontSize=10,
            fontWeight="bold", color=TEXT_HI,
        ).encode(
            x=alt.X("month:N", sort=df["month"].tolist()),
            y="cost_to_rev:Q", text="label_text:N",
        )
    )
st.altair_chart(style_chart(eff_chart.properties(title=f"Cost-to-revenue · avg {avg_eff:.1f}%"),
                              260), use_container_width=True)


# ─── 11. SCENARIO ANALYSIS ──────────────────────────────────
st.markdown("---")
st.markdown("## 11. SCENARIO ANALYSIS — WHAT IF?")
st.caption("Adjust the levers below. Each slider re-computes profit for the selected period.")

sc1, sc2, sc3 = st.columns(3)
with sc1:
    rev_adj = st.slider("Revenue Δ", -30, 30, 0, 1, format="%d%%", key="sc_rev")
with sc2:
    salary_adj = st.slider("Salary Δ", -30, 30, 0, 1, format="%d%%", key="sc_sal")
with sc3:
    other_adj = st.slider("Other costs Δ", -30, 30, 0, 1, format="%d%%", key="sc_other")

scen_rev = total_rev * (1 + rev_adj / 100)
scen_salary = df["salary"].sum() * (1 + salary_adj / 100)
other_total = total_exp - df["salary"].sum()
scen_other = other_total * (1 + other_adj / 100)
scen_exp = scen_salary + scen_other
scen_profit = scen_rev - scen_exp
scen_gm = (scen_profit / scen_rev * 100) if scen_rev else 0

scen_rows = pd.DataFrame([
    {"label": "Current Revenue", "value": total_rev, "kind": "Revenue"},
    {"label": "Scenario Revenue", "value": scen_rev, "kind": "Revenue"},
    {"label": "Current Profit", "value": total_profit, "kind": "Profit"},
    {"label": "Scenario Profit", "value": scen_profit, "kind": "Profit"},
])
scen_rows["value_scaled"] = scen_rows["value"].apply(scale)
scen_rows["label_text"] = scen_rows["value"].apply(fmt_chart_label)

scen_chart = (
    alt.Chart(scen_rows)
    .mark_bar(size=55, cornerRadiusEnd=3)
    .encode(
        x=alt.X("label:N", sort=scen_rows["label"].tolist(), title=None,
                axis=alt.Axis(labelAngle=-15)),
        y=alt.Y("value_scaled:Q", title=f"Amount ({unit})"),
        color=alt.Color("kind:N",
                         scale=alt.Scale(domain=["Revenue", "Profit"], range=[ACCENT, SUCCESS]),
                         legend=alt.Legend(orient="top", title=None)),
        tooltip=["label", alt.Tooltip("value:Q", format=",.0f")],
    )
)
if show_labels:
    scen_chart = scen_chart + (
        alt.Chart(scen_rows).mark_text(
            align="center", baseline="bottom", dy=-4, fontSize=11,
            fontWeight="bold", color=TEXT_HI,
        ).encode(
            x=alt.X("label:N", sort=scen_rows["label"].tolist()),
            y="value_scaled:Q", text="label_text:N",
        )
    )

c1, c2 = st.columns([3, 2])
with c1:
    st.altair_chart(style_chart(scen_chart, 280), use_container_width=True)
with c2:
    delta_profit = scen_profit - total_profit
    sign = "+" if delta_profit >= 0 else ""
    kpi_tile(
        f"{sign}{fmt_short_inr(delta_profit)}",
        "Profit Δ vs current",
        actual=f"Scenario profit {fmt_short_inr(scen_profit)} ({scen_gm:.1f}% GM)",
        sub=f"Rev {rev_adj:+d}% · Salary {salary_adj:+d}% · Other {other_adj:+d}%",
        accent_color=SUCCESS if delta_profit >= 0 else DANGER,
    )
    if abs(rev_adj) + abs(salary_adj) + abs(other_adj) > 0:
        st.caption(f"💡 If you achieved this scenario, FY profit moves "
                    f"from {fmt_short_inr(total_profit)} → {fmt_short_inr(scen_profit)}.")


# ─── 12. KEY INSIGHTS ────────────────────────────────────────
st.markdown("---")
st.markdown("## 12. KEY INSIGHTS")

df_sorted = df.sort_values("month_dt").reset_index(drop=True)
df_sorted["rev_delta"] = df_sorted["total_rev"].diff()
df_sorted["profit_delta"] = df_sorted["profit"].diff()
biggest_rev_jump = (df_sorted.loc[df_sorted["rev_delta"].idxmax()]
                    if df_sorted["rev_delta"].notna().any() else None)
biggest_profit_swing = (df_sorted.loc[df_sorted["profit_delta"].abs().idxmax()]
                        if df_sorted["profit_delta"].notna().any() else None)
highest_cost = df.loc[df["total_exp"].idxmax()]
best_gm = df.loc[df["gm_pct"].idxmax()]
cost_to_rev = (df["total_exp"].sum() / df["total_rev"].sum() * 100) if df["total_rev"].sum() else 0
ultra_pct = df["ultra_rev"].sum() / df["total_rev"].sum() * 100 if df["total_rev"].sum() else 0
loss_count = len(df[df["profit"] < 0])
trail3 = df["total_rev"].tail(3).mean() if len(df) >= 3 else df["total_rev"].mean()
run_vs_avg = (trail3 - avg_rev) / avg_rev * 100 if avg_rev else 0


def insight_card(title: str, value: str, sub: str, color: str = ACCENT):
    st.markdown(
        f'<div style="background:{BG_PANEL}; border:1px solid {BORDER}; '
        f'border-left:3px solid {color}; padding:1rem 1.2rem; border-radius:8px; '
        f'height:100%; box-shadow:0 1px 3px rgba(15,23,42,0.04);">'
        f'<div style="color:{TEXT_MUTED}; font-size:0.7rem; font-weight:600; '
        f'text-transform:uppercase; letter-spacing:0.1em;">{title}</div>'
        f'<div style="color:{TEXT_HI}; font-size:1.25rem; font-weight:700; '
        f'margin-top:0.3rem;">{value}</div>'
        f'<div style="color:{TEXT_MID}; font-size:0.82rem; margin-top:0.25rem;">{sub}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


c1, c2, c3 = st.columns(3)
with c1:
    insight_card("🏆 Best Margin Month", best_gm["month"],
                 f"{best_gm['gm_pct']:.1f}% · profit {fmt_short_inr(best_gm['profit'])}", SUCCESS)
with c2:
    insight_card("💰 Highest Cost Month", highest_cost["month"],
                 f"Expenses {fmt_short_inr(highest_cost['total_exp'])}", WARN)
with c3:
    insight_card("⚖️ Cost-to-Revenue", f"{cost_to_rev:.1f}%",
                 f"₹100 revenue → ₹{cost_to_rev:.0f} costs", ACCENT)

c4, c5, c6 = st.columns(3)
with c4:
    if biggest_rev_jump is not None and pd.notna(biggest_rev_jump["rev_delta"]):
        insight_card("📈 Biggest Revenue Jump", biggest_rev_jump["month"],
                     f"+{fmt_short_inr(biggest_rev_jump['rev_delta'])} vs prior", SUCCESS)
with c5:
    if biggest_profit_swing is not None and pd.notna(biggest_profit_swing["profit_delta"]):
        d = biggest_profit_swing["profit_delta"]
        sign = "+" if d > 0 else ""
        insight_card("🔁 Biggest Profit Swing", biggest_profit_swing["month"],
                     f"{sign}{fmt_short_inr(d)} vs prior",
                     SUCCESS if d > 0 else DANGER)
with c6:
    insight_card("🎯 Ultra Concentration", f"{ultra_pct:.0f}%",
                 f"{100 - ultra_pct:.0f}% Premium · diversify risk",
                 ACCENT_VIOLET)

c7, c8, c9 = st.columns(3)
with c7:
    insight_card("⚠️ Loss Months", str(loss_count),
                 f"of {len(df)} months · {(loss_count/len(df)*100):.0f}% loss rate",
                 DANGER if loss_count > 0 else SUCCESS)
with c8:
    sign = "+" if run_vs_avg >= 0 else ""
    insight_card("📊 Trailing-3M vs Period Avg",
                  f"{sign}{run_vs_avg:.1f}%",
                  f"Last 3-mo avg: {fmt_short_inr(trail3)} vs period {fmt_short_inr(avg_rev)}",
                  SUCCESS if run_vs_avg >= 0 else DANGER)
with c9:
    # Operating leverage: how much profit grows for 1% revenue change
    if len(df_sorted) >= 2 and df_sorted["rev_delta"].abs().sum() > 0:
        # Average sensitivity
        rev_pct = df_sorted["total_rev"].pct_change().abs().mean() * 100
        prof_pct = df_sorted["profit"].pct_change().abs().mean() * 100
        leverage = prof_pct / rev_pct if rev_pct else 0
        insight_card("⚙️ Operating Leverage", f"{leverage:.1f}x",
                     "Profit % change per 1% revenue change (avg)",
                     ACCENT_DEEP)


# ─── 13. RAW DATA ────────────────────────────────────────────
st.markdown("---")
with st.expander("📋 RAW DATA (filtered range)"):
    show_cols = ["month", "ultra_rev", "premium_rev", "total_rev",
                 "total_exp", "profit", "gm_pct"]
    df_show = df[show_cols].copy()
    for c in ["ultra_rev", "premium_rev", "total_rev", "total_exp", "profit"]:
        df_show[c] = df_show[c].apply(lambda v: f"₹{v:,.0f}")
    df_show["gm_pct"] = df_show["gm_pct"].apply(lambda v: f"{v:.1f}%")
    st.dataframe(df_show, use_container_width=True, hide_index=True)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇ DOWNLOAD CSV", data=csv,
        file_name=f"insights_{selected_fy}.csv", mime="text/csv",
    )


st.markdown("---")
brand_bar("MEASURE · ANALYZE · DECIDE")
