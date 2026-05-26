"""ABC Analytics — Home dashboard.
Run: streamlit run Dashboard.py
Or double-click launch_dashboard.bat
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

from pnl_reader import read_pnl
from theme import (
    ACCENT,
    ACCENT_DEEP,
    ACCENT_SOFT_BG,
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
from year_analyzer import _fy_for_month, analyze_year

st.set_page_config(
    page_title="ABC Dashboard · ",
    page_icon="💪",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()
sidebar_branding()

from data_sources import require_master_or_stop
require_master_or_stop()


# ─── Refresh control (sidebar) ─────────────────────────────
with st.sidebar:
    st.markdown(
        f'<div style="color:{TEXT_MUTED}; font-size:0.7rem; font-weight:700; '
        f'text-transform:uppercase; letter-spacing:0.12em; margin-bottom:0.3rem;">'
        f'🔄 REFRESH</div>',
        unsafe_allow_html=True,
    )
    refresh_mode = st.selectbox(
        "Refresh mode",
        ["AI only (fast)", "Pipeline + AI (full)", "Pipeline only"],
        label_visibility="collapsed",
        key="refresh_mode",
    )
    if st.button("Run refresh", use_container_width=True, key="run_refresh_btn"):
        from data_sources import active_source as _src  # noqa: PLC0415
        from refresh_all import run_refresh  # noqa: PLC0415

        skip_pipe = refresh_mode == "AI only (fast)"
        skip_ai = refresh_mode == "Pipeline only"
        status = st.empty()
        log_panel = st.empty()
        log: list[str] = []
        with st.spinner("Refreshing — this may take several minutes …"):
            for label, ok, detail in run_refresh(
                source=_src().key, skip_pipeline=skip_pipe, skip_ai=skip_ai,
            ):
                flag = "✓" if ok else "✗"
                line = f"{flag} {label}"
                log.append(line)
                status.markdown(f"**{line}**")
                log_panel.code("\n".join(log[-15:]), language=None)
        st.cache_data.clear()
        st.success("Refresh complete — reloading data …")
        st.rerun()
    st.markdown("---")


# ─── Hero header ───────────────────────────────────────────
col_logo, col_title = st.columns([1, 5])
with col_logo:
    show_logo(width=140)
with col_title:
    st.title("ABC FITNESS CLUB")
    st.markdown(
        f'<div style="color:{TEXT_MUTED}; font-size:1.0rem; font-weight:500; '
        f'letter-spacing:0.01em;">{t("subtitle_home")}</div>',
        unsafe_allow_html=True,
    )

quote_banner()


# ─── Load data ─────────────────────────────────────────────
@st.cache_data
def load_data():
    months = read_pnl()
    yr = analyze_year(months)
    return months, yr


try:
    months, yr = load_data()
except Exception as e:
    st.error(f"{t('err_data_load')}: {e}")
    st.info(t("info_master_file"))
    st.stop()


df = pd.DataFrame([
    {
        "month_dt": m.month,
        "month": m.label,
        "fy": _fy_for_month(m.month),
        "total_rev": m.total_rev,
        "total_exp": m.total_exp,
        "profit": m.profit,
        "gm_pct": m.gm_pct * 100,
        "ultra_rev": m.ultra_rev,
        "premium_rev": m.premium_rev,
    }
    for m in months
])

total_rev = df["total_rev"].sum()
total_exp = df["total_exp"].sum()
total_profit = df["profit"].sum()
avg_gm = (total_profit / total_rev * 100) if total_rev else 0
latest = df.iloc[-1]
prev = df.iloc[-2] if len(df) >= 2 else latest


def delta_pct(curr: float, prior: float) -> str:
    if not prior:
        return ""
    pct = (curr - prior) / abs(prior) * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}% vs {prev['month']}"


def delta_positive(curr: float, prior: float, lower_is_better: bool = False) -> bool:
    if lower_is_better:
        return curr <= prior
    return curr >= prior


# ─── SECTION 1 — Headline KPIs ─────────────────────────────
st.markdown(f"## 1. {t('stats_that_matter')} · FY{yr.fy_label}")
k1, k2, k3, k4 = st.columns(4)
with k1:
    kpi_tile(
        fmt_short_inr(total_rev), t("total_revenue"),
        actual=fmt_inr(total_rev),
        sub=f"{len(df)} months · Apr 2025 → Mar 2026",
        accent_color=ACCENT,
    )
with k2:
    kpi_tile(
        fmt_short_inr(total_exp), t("operating_cost"),
        actual=fmt_inr(total_exp),
        sub=f"Avg {fmt_short_inr(total_exp/len(df))}/mo",
        accent_color=WARN,
    )
with k3:
    kpi_tile(
        fmt_short_inr(total_profit), t("net_profit"),
        actual=fmt_inr(total_profit),
        sub=f"{len(yr.loss_months)} loss month(s)",
        accent_color=SUCCESS if total_profit >= 0 else DANGER,
    )
with k4:
    kpi_tile(
        fmt_pct(avg_gm), t("gross_margin"),
        actual=f"Best {fmt_pct(df['gm_pct'].max())} · Worst {fmt_pct(df['gm_pct'].min())}",
        sub=f"Median {fmt_pct(df['gm_pct'].median())}",
        accent_color=ACCENT_VIOLET,
    )


# ─── SECTION 2 — Trend at-a-glance (chart, not text) ───────
st.markdown(f"## 2. REVENUE & PROFIT TREND")


def style_chart(c: alt.Chart, height: int) -> alt.Chart:
    return (
        c.configure(background=BG_PANEL)
        .configure_view(stroke=BORDER, strokeWidth=1)
        .configure_axis(
            labelColor=TEXT_MID, titleColor=TEXT_MUTED, gridColor=BORDER,
            domainColor=BORDER, tickColor=BORDER, labelFontSize=11, titleFontSize=11,
        )
        .configure_legend(labelColor=TEXT_MID, titleColor=TEXT_MUTED)
        .configure_title(color=TEXT_HI, fontSize=13, anchor="start")
        .properties(height=height, background=BG_PANEL)
    )


df_trend = df.copy()
df_trend["rev_L"] = df_trend["total_rev"] / 1e5
df_trend["profit_L"] = df_trend["profit"] / 1e5

c1, c2 = st.columns([3, 2])
with c1:
    long_df = df_trend.melt(
        id_vars=["month", "total_rev", "profit"],
        value_vars=["rev_L", "profit_L"],
        var_name="metric", value_name="amount",
    )
    long_df["metric"] = long_df["metric"].map({"rev_L": "Revenue", "profit_L": "Profit"})
    long_df["label_text"] = long_df.apply(
        lambda r: fmt_chart_label(r["total_rev"] if r["metric"] == "Revenue" else r["profit"]),
        axis=1,
    )
    line = (
        alt.Chart(long_df)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=70), strokeWidth=2.8)
        .encode(
            x=alt.X("month:N", sort=df["month"].tolist(), title=None,
                    axis=alt.Axis(labelAngle=-30)),
            y=alt.Y("amount:Q", title="₹ Lakhs"),
            color=alt.Color(
                "metric:N",
                scale=alt.Scale(domain=["Revenue", "Profit"], range=[ACCENT, SUCCESS]),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=["month", "metric", alt.Tooltip("amount:Q", format=".2f")],
        )
    )
    # Two text layers so Revenue + Profit labels never collide vertically
    text_rev = (
        alt.Chart(long_df[long_df["metric"] == "Revenue"]).mark_text(
            align="center", baseline="bottom", dy=-9, fontSize=12,
            fontWeight="bold", color=ACCENT_DEEP,
        ).encode(
            x=alt.X("month:N", sort=df["month"].tolist()),
            y="amount:Q", text="label_text:N",
        )
    )
    text_profit = (
        alt.Chart(long_df[long_df["metric"] == "Profit"]).mark_text(
            align="center", baseline="top", dy=12, fontSize=12,
            fontWeight="bold", color=SUCCESS,
        ).encode(
            x=alt.X("month:N", sort=df["month"].tolist()),
            y="amount:Q", text="label_text:N",
        )
    )
    chart = (line + text_rev + text_profit).properties(
        title="Monthly revenue and profit (₹ Lakhs)",
    )
    st.altair_chart(style_chart(chart, 360), use_container_width=True)

with c2:
    bar_df = df_trend.copy()
    bar_df["state"] = bar_df["profit"].apply(lambda v: "Loss" if v < 0 else "Profit")
    bar_df["label_text"] = bar_df["gm_pct"].apply(lambda v: f"{v:.0f}%")
    bars = (
        alt.Chart(bar_df)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=alt.X("month:N", sort=df["month"].tolist(), title=None,
                    axis=alt.Axis(labelAngle=-30)),
            y=alt.Y("gm_pct:Q", title="GM (%)"),
            color=alt.Color(
                "state:N",
                scale=alt.Scale(domain=["Profit", "Loss"], range=[SUCCESS, DANGER]),
                legend=None,
            ),
            tooltip=["month", alt.Tooltip("gm_pct:Q", format=".1f")],
        )
    )
    label = alt.Chart(bar_df).mark_text(
        align="center", baseline="bottom", dy=-5, fontSize=12,
        fontWeight="bold", color=TEXT_HI,
    ).encode(
        x=alt.X("month:N", sort=df["month"].tolist()),
        y="gm_pct:Q", text="label_text:N",
    )
    chart = (bars + label).properties(title="Gross margin %")
    st.altair_chart(style_chart(chart, 360), use_container_width=True)


# ─── SECTION 3 — Latest month spotlight (with deltas) ──────
st.markdown(f"## 3. {t('latest_month')} · {str(latest['month']).upper()}")
m1, m2, m3, m4 = st.columns(4)
with m1:
    kpi_tile(
        fmt_short_inr(latest["total_rev"]), t("revenue"),
        actual=fmt_inr(latest["total_rev"]),
        delta=delta_pct(latest["total_rev"], prev["total_rev"]),
        delta_positive=delta_positive(latest["total_rev"], prev["total_rev"]),
        accent_color=ACCENT,
    )
with m2:
    kpi_tile(
        fmt_short_inr(latest["total_exp"]), t("expenses"),
        actual=fmt_inr(latest["total_exp"]),
        delta=delta_pct(latest["total_exp"], prev["total_exp"]),
        delta_positive=delta_positive(latest["total_exp"], prev["total_exp"], lower_is_better=True),
        accent_color=WARN,
    )
with m3:
    kpi_tile(
        fmt_short_inr(latest["profit"]), t("profit"),
        actual=fmt_inr(latest["profit"]),
        delta=delta_pct(latest["profit"], prev["profit"]),
        delta_positive=delta_positive(latest["profit"], prev["profit"]),
        accent_color=SUCCESS if latest["profit"] >= 0 else DANGER,
    )
with m4:
    kpi_tile(
        fmt_pct(latest["gm_pct"]), t("gross_margin"),
        actual=f"Prev: {fmt_pct(prev['gm_pct'])}",
        delta=f"{'+' if latest['gm_pct']>=prev['gm_pct'] else ''}{latest['gm_pct']-prev['gm_pct']:.1f}pp",
        delta_positive=latest["gm_pct"] >= prev["gm_pct"],
        accent_color=ACCENT_VIOLET,
    )


# ─── SECTION 4 — Year highlights ───────────────────────────
st.markdown(f"## 4. {t('year_highlights')}")
profit_stat = yr.line_stats['profit']
c1, c2 = st.columns(2)
with c1:
    st.markdown(
        f'<div style="background:{BG_PANEL}; border:1px solid {BORDER}; '
        f'border-left:4px solid {SUCCESS}; padding:1.2rem 1.4rem; border-radius:8px;">'
        f'<div style="color:{TEXT_MUTED}; font-size:0.72rem; font-weight:600; '
        f'text-transform:uppercase; letter-spacing:0.1em;">{t("best_profit_month")}</div>'
        f'<div style="color:{TEXT_HI}; font-size:1.35rem; font-weight:700; margin-top:0.3rem;">'
        f'{profit_stat.max_month}</div>'
        f'<div style="color:{SUCCESS}; font-size:2.0rem; font-weight:800; letter-spacing:-0.025em; '
        f'margin-top:0.15rem;">{fmt_short_inr(profit_stat.max_value)}</div>'
        f'<div style="color:{TEXT_MUTED}; font-size:0.78rem; margin-top:0.15rem;">'
        f'{fmt_inr(profit_stat.max_value)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        f'<div style="background:{BG_PANEL}; border:1px solid {BORDER}; '
        f'border-left:4px solid {DANGER}; padding:1.2rem 1.4rem; border-radius:8px;">'
        f'<div style="color:{TEXT_MUTED}; font-size:0.72rem; font-weight:600; '
        f'text-transform:uppercase; letter-spacing:0.1em;">{t("worst_profit_month")}</div>'
        f'<div style="color:{TEXT_HI}; font-size:1.35rem; font-weight:700; margin-top:0.3rem;">'
        f'{profit_stat.min_month}</div>'
        f'<div style="color:{DANGER}; font-size:2.0rem; font-weight:800; letter-spacing:-0.025em; '
        f'margin-top:0.15rem;">{fmt_short_inr(profit_stat.min_value)}</div>'
        f'<div style="color:{TEXT_MUTED}; font-size:0.78rem; margin-top:0.15rem;">'
        f'{fmt_inr(profit_stat.min_value)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─── SECTION 5 — Revenue mix (Ultra vs Premium) ────────────
st.markdown("## 5. REVENUE MIX")
ultra_total = df["ultra_rev"].sum()
premium_total = df["premium_rev"].sum()
mix_df = pd.DataFrame({"segment": ["Ultra", "Premium"],
                        "amount": [ultra_total, premium_total]})
mix_df["pct"] = mix_df["amount"] / mix_df["amount"].sum() * 100

c1, c2 = st.columns([2, 3])
with c1:
    mix_df["pct_label"] = mix_df["pct"].apply(lambda v: f"{v:.0f}%")
    donut = (
        alt.Chart(mix_df)
        .mark_arc(innerRadius=85, outerRadius=160, stroke=BG_PANEL, strokeWidth=3)
        .encode(
            theta="amount:Q",
            color=alt.Color(
                "segment:N",
                scale=alt.Scale(domain=["Ultra", "Premium"], range=[ACCENT, ACCENT_VIOLET]),
                legend=alt.Legend(orient="bottom", title=None),
            ),
            tooltip=["segment", alt.Tooltip("amount:Q", format=",.0f"),
                     alt.Tooltip("pct:Q", format=".1f")],
        )
        .properties(title=f"Total revenue mix · {fmt_short_inr(total_rev)}")
    )
    donut_text = (
        alt.Chart(mix_df).mark_text(
            radius=125, fontSize=14, fontWeight="bold", color=TEXT_HI,
        ).encode(
            theta=alt.Theta("amount:Q", stack=True),
            text="pct_label:N",
        )
    )
    st.altair_chart(style_chart(donut + donut_text, 400), use_container_width=True)

with c2:
    rev_stack = df.melt(
        id_vars=["month", "total_rev"], value_vars=["ultra_rev", "premium_rev"],
        var_name="segment", value_name="amount",
    )
    rev_stack["segment"] = rev_stack["segment"].map(
        {"ultra_rev": "Ultra", "premium_rev": "Premium"}
    )
    rev_stack["amount_L"] = rev_stack["amount"] / 1e5

    base = (
        alt.Chart(rev_stack)
        .mark_area(opacity=0.85, line={"strokeWidth": 2.5})
        .encode(
            x=alt.X("month:N", sort=df["month"].tolist(), title=None,
                    axis=alt.Axis(labelAngle=-30)),
            y=alt.Y("amount_L:Q", title="₹ Lakhs", stack="zero"),
            color=alt.Color(
                "segment:N",
                scale=alt.Scale(domain=["Ultra", "Premium"], range=[ACCENT, ACCENT_VIOLET]),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=["month", "segment", alt.Tooltip("amount:Q", format=",.0f")],
        )
    )
    totals = df.copy()
    totals["total_L"] = totals["total_rev"] / 1e5
    totals["label_text"] = totals["total_rev"].apply(fmt_chart_label)
    label_layer = (
        alt.Chart(totals).mark_text(
            align="center", baseline="bottom", dy=-5, fontSize=12,
            fontWeight="bold", color=TEXT_HI,
        ).encode(
            x=alt.X("month:N", sort=df["month"].tolist()),
            y="total_L:Q", text="label_text:N",
        )
    )
    chart = (base + label_layer).properties(title="Monthly revenue by segment")
    st.altair_chart(style_chart(chart, 400), use_container_width=True)


# ─── Footer ───────────────────────────────────────────────
st.markdown("---")
brand_bar(t("brand_bar_footer"))
