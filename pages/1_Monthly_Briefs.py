"""Monthly Briefs — branded reader with PDF export + mini context KPIs."""
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import altair as alt
import pandas as pd
import streamlit as st

from output_paths import BRIEFS_DIR
from pdf_export import markdown_to_pdf
from pnl_reader import read_pnl
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

st.set_page_config(page_title="Monthly Briefs · ABC", page_icon="📝", layout="wide")
inject_theme()
sidebar_branding()

from data_sources import require_master_or_stop
require_master_or_stop()

col_logo, col_title = st.columns([1, 5])
with col_logo:
    show_logo(width=120)
with col_title:
    st.title(f"1. {t('page_briefs_title')}")
    st.markdown(
        f'<div style="color:{TEXT_MUTED}; font-size:0.95rem; font-weight:500;">'
        f'{t("page_briefs_sub")}</div>',
        unsafe_allow_html=True,
    )

quote_banner()

BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
brief_files = sorted(BRIEFS_DIR.glob("*.md"))
if not brief_files:
    try:
        from pnl_reader import read_pnl  # noqa: PLC0415
        _ms = read_pnl()
        _n = len(_ms)
        _latest = _ms[-1].label if _ms else ""
    except Exception:
        _n, _latest = 0, ""
    _extra = f" Latest: <b>{_latest}</b>." if _latest else ""
    st.markdown(
        f"""
<div style="background:#FFFFFF; border:1px solid #E2E8F0; border-left:4px solid #0EA5E9;
            border-radius:10px; padding:1.8rem 2rem; box-shadow:0 1px 3px rgba(15,23,42,0.04);">
<div style="font-size:1.1rem; font-weight:700; color:#0F172A;">📝 No monthly briefs generated yet</div>
<div style="color:#334155; font-size:0.95rem; margin-top:0.6rem; line-height:1.55;">
Your master Excel has <b>{_n} month(s)</b> of data.{_extra} Monthly briefs are
AI-written one-page narratives — best line, worst line, what changed, and the
single action a busy owner should take next.
</div>
<div style="color:#64748B; font-size:0.85rem; margin-top:0.95rem;">
<b>Generate:</b> click <b>🔄 Refresh → AI only (fast) → Run refresh</b> on the
Home page, or run <code>python narrate_month.py</code> from this workspace.
</div></div>""",
        unsafe_allow_html=True,
    )
    st.stop()

options = {}
for f in brief_files:
    match = re.search(r"monthly_brief_(\d{4}-\d{2})", f.name)
    if match:
        options[match.group(1)] = f

if not options:
    st.error("No briefs with expected naming pattern found.")
    st.stop()


# ─── Selector + downloads ──────────────────────────────────
st.markdown(f"### {t('n_briefs_available', n=len(options))}")
col1, col2 = st.columns([4, 1])
with col1:
    selected_month = st.selectbox(t("select_month"), sorted(options.keys(), reverse=True))

brief_path = options[selected_month]
content = brief_path.read_text(encoding="utf-8")

with col2:
    st.markdown("&nbsp;")
    try:
        pdf_title = f"Monthly Brief · {selected_month}"
        pdf_subtitle = f"ABC Fitness Club · {datetime.now().strftime('%d %b %Y')}"
        pdf_bytes = markdown_to_pdf(content, pdf_title, pdf_subtitle)
        st.download_button(
            t("download_pdf"), data=pdf_bytes,
            file_name=f"monthly_brief_{selected_month}.pdf",
            mime="application/pdf", use_container_width=True,
            key=f"pdf_{selected_month}",
        )
    except Exception as e:
        st.button("PDF unavailable", use_container_width=True, disabled=True)
        st.caption(f"⚠ {e}")


# ─── Mini KPIs for THIS month (sourced from raw P&L) ───────
try:
    months = read_pnl()
    df = pd.DataFrame([{
        "month_dt": m.month, "month": m.month.strftime("%Y-%m"),
        "label": m.label, "total_rev": m.total_rev,
        "total_exp": m.total_exp, "profit": m.profit,
        "gm_pct": m.gm_pct * 100,
    } for m in months])
    df = df.sort_values("month_dt").reset_index(drop=True)

    row = df[df["month"] == selected_month]
    if not row.empty:
        idx = row.index[0]
        cur = df.iloc[idx]
        prev = df.iloc[idx - 1] if idx > 0 else cur

        st.markdown(f"#### {cur['label']} · KEY METRICS")
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            kpi_tile(
                fmt_short_inr(cur["total_rev"]), t("total_revenue"),
                actual=fmt_inr(cur["total_rev"]),
                delta=(f"{'+' if cur['total_rev']>=prev['total_rev'] else ''}"
                       f"{(cur['total_rev']-prev['total_rev'])/abs(prev['total_rev'])*100:.1f}% vs prev"
                       if idx > 0 and prev["total_rev"] else ""),
                delta_positive=cur["total_rev"] >= prev["total_rev"],
                accent_color=ACCENT,
            )
        with k2:
            kpi_tile(
                fmt_short_inr(cur["total_exp"]), t("operating_cost"),
                actual=fmt_inr(cur["total_exp"]),
                delta=(f"{'+' if cur['total_exp']>=prev['total_exp'] else ''}"
                       f"{(cur['total_exp']-prev['total_exp'])/abs(prev['total_exp'])*100:.1f}% vs prev"
                       if idx > 0 and prev["total_exp"] else ""),
                delta_positive=cur["total_exp"] <= prev["total_exp"],
                accent_color=WARN,
            )
        with k3:
            kpi_tile(
                fmt_short_inr(cur["profit"]), t("net_profit"),
                actual=fmt_inr(cur["profit"]),
                delta=(f"{'+' if cur['profit']>=prev['profit'] else ''}"
                       f"{fmt_short_inr(cur['profit']-prev['profit'])} vs prev"
                       if idx > 0 else ""),
                delta_positive=cur["profit"] >= prev["profit"],
                accent_color=SUCCESS if cur["profit"] >= 0 else DANGER,
            )
        with k4:
            kpi_tile(
                fmt_pct(cur["gm_pct"]), t("gross_margin"),
                actual=f"Prev: {fmt_pct(prev['gm_pct'])}",
                delta=(f"{'+' if cur['gm_pct']>=prev['gm_pct'] else ''}"
                       f"{cur['gm_pct']-prev['gm_pct']:.1f}pp"
                       if idx > 0 else ""),
                delta_positive=cur["gm_pct"] >= prev["gm_pct"],
                accent_color=ACCENT_VIOLET,
            )

        # Inline mini-trend (last 6 months around the selected one)
        win_start = max(0, idx - 5)
        sub = df.iloc[win_start:idx + 1].copy()
        sub["rev_L"] = sub["total_rev"] / 1e5
        sub["label_text"] = sub["total_rev"].apply(fmt_chart_label)
        area = (
            alt.Chart(sub)
            .mark_area(opacity=0.25, color=ACCENT)
            .encode(
                x=alt.X("label:N", sort=sub["label"].tolist(), title=None,
                        axis=alt.Axis(labelAngle=-30)),
                y=alt.Y("rev_L:Q", title="Revenue ₹L"),
                tooltip=["label", alt.Tooltip("total_rev:Q", format=",.0f")],
            )
        )
        line = (
            alt.Chart(sub)
            .mark_line(point=True, color=ACCENT, strokeWidth=2.5)
            .encode(x=alt.X("label:N", sort=sub["label"].tolist()), y="rev_L:Q")
        )
        labels = (
            alt.Chart(sub).mark_text(
                align="center", baseline="bottom", dy=-8, fontSize=10,
                fontWeight="bold", color=ACCENT_DEEP,
            ).encode(
                x=alt.X("label:N", sort=sub["label"].tolist()),
                y="rev_L:Q", text="label_text:N",
            )
        )
        st.altair_chart(
            (area + line + labels)
            .configure(background=BG_PANEL)
            .configure_view(stroke=BORDER, strokeWidth=1)
            .configure_axis(labelColor=TEXT_MID, titleColor=TEXT_MUTED,
                            gridColor=BORDER, domainColor=BORDER, tickColor=BORDER)
            .configure_title(color=TEXT_HI, fontSize=12, anchor="start")
            .properties(height=210, title=f"Revenue trend · last {len(sub)} months",
                        background=BG_PANEL),
            use_container_width=True,
        )
except Exception as e:
    st.caption(f"⚠ Couldn't load context KPIs: {e}")


# ─── Brief content ─────────────────────────────────────────
st.caption(f"{t('source_label')} `{brief_path.name}`")
st.markdown("---")
st.markdown(
    f'<div style="background:{BG_PANEL}; border:1px solid {BORDER}; '
    f'border-top:3px solid {ACCENT}; padding:1.8rem 2rem; border-radius:10px;">',
    unsafe_allow_html=True,
)
st.markdown(content)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")
brand_bar(t("brand_bar_monthly"))
