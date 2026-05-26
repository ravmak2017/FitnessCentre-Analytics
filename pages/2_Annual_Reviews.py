"""Annual Reviews — branded reader with PDF export + headline KPIs."""
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import altair as alt
import pandas as pd
import streamlit as st

from output_paths import ANNUAL_DIR
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
from year_analyzer import _fy_for_month, analyze_year

st.set_page_config(page_title="Annual Reviews · ABC", page_icon="📅", layout="wide")
inject_theme()
sidebar_branding()

from data_sources import require_master_or_stop
require_master_or_stop()

col_logo, col_title = st.columns([1, 5])
with col_logo:
    show_logo(width=120)
with col_title:
    st.title(f"2. {t('page_annual_title')}")
    st.markdown(
        f'<div style="color:{TEXT_MUTED}; font-size:0.95rem; font-weight:500;">'
        f'{t("page_annual_sub")}</div>',
        unsafe_allow_html=True,
    )

quote_banner()

ANNUAL_DIR.mkdir(parents=True, exist_ok=True)
all_files = sorted(ANNUAL_DIR.glob("*.md"))
if not all_files:
    try:
        from pnl_reader import read_pnl  # noqa: PLC0415
        _ms = read_pnl()
        _n = len(_ms)
        _first = _ms[0].label if _ms else ""
        _last = _ms[-1].label if _ms else ""
    except Exception:
        _n, _first, _last = 0, "", ""
    _cov = f" ({_first} → {_last})" if _first else ""
    st.markdown(
        f"""
<div style="background:#FFFFFF; border:1px solid #E2E8F0; border-left:4px solid #7C3AED;
            border-radius:10px; padding:1.8rem 2rem; box-shadow:0 1px 3px rgba(15,23,42,0.04);">
<div style="font-size:1.1rem; font-weight:700; color:#0F172A;">📅 Annual review not yet generated</div>
<div style="color:#334155; font-size:0.95rem; margin-top:0.6rem; line-height:1.55;">
Coverage so far: <b>{_n} of 12 months</b>{_cov}. Annual reviews are most
informative once 6+ months are loaded, but a mid-year snapshot is still useful
for board-style reviews and course-correction.
</div>
<div style="color:#334155; font-size:0.92rem; margin-top:0.6rem; line-height:1.55;">
Two versions are produced from the same data: an <b>Owner version</b>
(narrative, forwardable to family or partners) and an <b>Accountant version</b>
(numerical, month-by-month, audit-friendly).
</div>
<div style="color:#64748B; font-size:0.85rem; margin-top:0.95rem;">
<b>Generate:</b> click <b>🔄 Refresh → AI only (fast)</b> on the Home page, or
run <code>python narrate_year.py</code>.
</div></div>""",
        unsafe_allow_html=True,
    )
    st.stop()

owner_files = [f for f in all_files if "owner" in f.name.lower()]
accountant_files = [f for f in all_files if "accountant" in f.name.lower()]

fy_pattern = re.compile(r"FY(\d{4}-\d{2})")
fy_options = sorted(
    {fy_pattern.search(f.name).group(1) for f in all_files if fy_pattern.search(f.name)},
    reverse=True,
)

if not fy_options:
    st.error("Couldn't parse FY from filenames.")
    st.stop()

col1, col2 = st.columns([1, 2])
with col1:
    selected_fy = st.selectbox(t("fiscal_year"), fy_options)
with col2:
    view = st.radio(
        t("audience"),
        [t("owner"), t("accountant"), t("side_by_side")],
        horizontal=True,
    )

owner = next((f for f in owner_files if selected_fy in f.name), None)
accountant = next((f for f in accountant_files if selected_fy in f.name), None)


# ─── FY headline KPIs ──────────────────────────────────────
try:
    months_all = read_pnl()
    yr = analyze_year(months_all, fy_label=selected_fy)
    df_fy = pd.DataFrame([{
        "month": m.label, "total_rev": m.total_rev,
        "total_exp": m.total_exp, "profit": m.profit,
        "gm_pct": m.gm_pct * 100,
    } for m in yr.months])
    total_rev = df_fy["total_rev"].sum()
    total_exp = df_fy["total_exp"].sum()
    total_profit = df_fy["profit"].sum()
    avg_gm = (total_profit / total_rev * 100) if total_rev else 0

    st.markdown(f"#### FY{selected_fy} · HEADLINE NUMBERS")
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        kpi_tile(fmt_short_inr(total_rev), t("total_revenue"),
                 actual=fmt_inr(total_rev), accent_color=ACCENT)
    with k2:
        kpi_tile(fmt_short_inr(total_exp), t("operating_cost"),
                 actual=fmt_inr(total_exp), accent_color=WARN)
    with k3:
        kpi_tile(fmt_short_inr(total_profit), t("net_profit"),
                 actual=fmt_inr(total_profit),
                 accent_color=SUCCESS if total_profit >= 0 else DANGER)
    with k4:
        kpi_tile(fmt_pct(avg_gm), t("gross_margin"),
                 actual=f"{len(yr.months)} months · {len(yr.loss_months)} loss",
                 accent_color=ACCENT_VIOLET)

    # Mini revenue+profit chart
    df_fy["rev_L"] = df_fy["total_rev"] / 1e5
    df_fy["profit_L"] = df_fy["profit"] / 1e5
    long_df = df_fy.melt(id_vars=["month", "total_rev", "profit"],
                          value_vars=["rev_L", "profit_L"],
                          var_name="metric", value_name="amount")
    long_df["metric"] = long_df["metric"].map({"rev_L": "Revenue", "profit_L": "Profit"})
    long_df["label_text"] = long_df.apply(
        lambda r: fmt_chart_label(r["total_rev"] if r["metric"] == "Revenue" else r["profit"]),
        axis=1,
    )
    line = (
        alt.Chart(long_df)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=70), strokeWidth=2.8)
        .encode(
            x=alt.X("month:N", sort=df_fy["month"].tolist(), title=None,
                    axis=alt.Axis(labelAngle=-30)),
            y=alt.Y("amount:Q", title="₹ Lakhs"),
            color=alt.Color("metric:N",
                             scale=alt.Scale(domain=["Revenue", "Profit"],
                                              range=[ACCENT, SUCCESS]),
                             legend=alt.Legend(orient="top", title=None)),
            tooltip=["month", "metric", alt.Tooltip("amount:Q", format=".2f")],
        )
    )
    # Revenue labels above the point, Profit labels below — no collision
    text_rev = alt.Chart(long_df[long_df["metric"] == "Revenue"]).mark_text(
        align="center", baseline="bottom", dy=-10, fontSize=12,
        fontWeight="bold", color=ACCENT_DEEP,
    ).encode(
        x=alt.X("month:N", sort=df_fy["month"].tolist()),
        y="amount:Q", text="label_text:N",
    )
    text_profit = alt.Chart(long_df[long_df["metric"] == "Profit"]).mark_text(
        align="center", baseline="top", dy=12, fontSize=12,
        fontWeight="bold", color=SUCCESS,
    ).encode(
        x=alt.X("month:N", sort=df_fy["month"].tolist()),
        y="amount:Q", text="label_text:N",
    )
    chart = line + text_rev + text_profit
    st.altair_chart(
        chart.configure(background=BG_PANEL)
        .configure_view(stroke=BORDER, strokeWidth=1)
        .configure_axis(labelColor=TEXT_MID, titleColor=TEXT_MUTED,
                        gridColor=BORDER, domainColor=BORDER, tickColor=BORDER)
        .configure_legend(labelColor=TEXT_MID, titleColor=TEXT_MUTED)
        .configure_title(color=TEXT_HI, fontSize=13, anchor="start")
        .properties(height=380, background=BG_PANEL,
                    title=f"FY{selected_fy} · Revenue & Profit (₹ Lakhs)"),
        use_container_width=True,
    )
except Exception as e:
    st.caption(f"⚠ Couldn't load FY KPIs: {e}")


st.markdown("---")


def render_brief(file_path: Path | None, title: str, key_prefix: str):
    if not file_path:
        st.warning(t("version_missing"))
        return
    content = file_path.read_text(encoding="utf-8")
    col_a, col_b = st.columns([5, 1])
    with col_a:
        st.markdown(f"### {title}")
        st.caption(f"📄 `{file_path.name}`")
    with col_b:
        try:
            pdf_bytes = markdown_to_pdf(
                content,
                f"Annual Review · FY{selected_fy}",
                f"{title} · {datetime.now().strftime('%d %b %Y')}",
            )
            st.download_button(
                t("download_pdf"), data=pdf_bytes,
                file_name=file_path.name.replace(".md", ".pdf"),
                mime="application/pdf", key=f"pdf_{key_prefix}",
                use_container_width=True,
            )
        except Exception as e:
            st.button("PDF unavailable", key=f"pdf_err_{key_prefix}",
                       disabled=True, use_container_width=True)
            st.caption(f"⚠ {e}")
    st.markdown(
        f'<div style="background:{BG_PANEL}; border:1px solid {BORDER}; '
        f'border-top:3px solid {ACCENT}; padding:1.8rem 2rem; border-radius:10px;">',
        unsafe_allow_html=True,
    )
    st.markdown(content)
    st.markdown('</div>', unsafe_allow_html=True)


if view == t("owner"):
    render_brief(owner, t("owner_version"), "owner")
elif view == t("accountant"):
    render_brief(accountant, t("accountant_version"), "accountant")
else:
    col_o, col_a = st.columns(2)
    with col_o:
        render_brief(owner, f"👤 {t('owner_version_short')}", "owner_sbs")
    with col_a:
        render_brief(accountant, f"📊 {t('accountant_version_short')}", "accountant_sbs")

st.markdown("---")
brand_bar(t("brand_bar_annual"))
