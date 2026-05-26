"""Anomaly Reports — branded reader + PDF export. KPI cards only (no chart)."""
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from output_paths import ANOMALIES_DIR
from pdf_export import markdown_to_pdf
from theme import (
    ACCENT_VIOLET,
    BG_PANEL,
    BORDER,
    DANGER,
    SUCCESS,
    TEXT_MUTED,
    WARN,
    brand_bar,
    inject_theme,
    kpi_tile,
    quote_banner,
    show_logo,
    sidebar_branding,
    t,
)

st.set_page_config(page_title="Anomaly Reports · ABC", page_icon="🚨", layout="wide")
inject_theme()
sidebar_branding()

from data_sources import require_master_or_stop
require_master_or_stop()

col_logo, col_title = st.columns([1, 5])
with col_logo:
    show_logo(width=120)
with col_title:
    st.title(f"3. {t('page_anomaly_title')}")
    st.markdown(
        f'<div style="color:{TEXT_MUTED}; font-size:0.95rem; font-weight:500;">'
        f'{t("page_anomaly_sub")}</div>',
        unsafe_allow_html=True,
    )

quote_banner()

ANOMALIES_DIR.mkdir(parents=True, exist_ok=True)
reports = sorted(ANOMALIES_DIR.glob("*.md"))
if not reports:
    try:
        from pnl_reader import read_pnl  # noqa: PLC0415
        _n = len(read_pnl())
    except Exception:
        _n = 0
    st.markdown(
        f"""
<div style="background:#FFFFFF; border:1px solid #E2E8F0; border-left:4px solid #16A34A;
            border-radius:10px; padding:1.8rem 2rem; box-shadow:0 1px 3px rgba(15,23,42,0.04);">
<div style="font-size:1.1rem; font-weight:700; color:#0F172A;">✅ No anomalies on file</div>
<div style="color:#334155; font-size:0.95rem; margin-top:0.6rem; line-height:1.55;">
The sentinel scan hasn't been run yet. With <b>{_n} month(s)</b> of data on
file, a scan completes in under a minute and produces a severity-graded report
per month: <b>CRITICAL</b> (revenue collapse, large unexpected expense),
<b>NEEDS REVIEW</b> (statistical outliers, GM compression),
<b>MINOR</b> (small deviations), <b>CLEAN</b> (passes all checks).
</div>
<div style="color:#334155; font-size:0.92rem; margin-top:0.6rem; line-height:1.55;">
A clean dataset returning zero issues is itself useful evidence for an
auditor or partner — it's the documented control, not just an absence of bad news.
</div>
<div style="color:#64748B; font-size:0.85rem; margin-top:0.95rem;">
<b>Generate:</b> click <b>🔄 Refresh → AI only (fast)</b> on the Home page, or
run <code>python sentinel.py --all</code>.
</div></div>""",
        unsafe_allow_html=True,
    )
    st.stop()


SEV_COLOR = {
    "CRITICAL": DANGER,
    "NEEDS REVIEW": WARN,
    "MINOR": ACCENT_VIOLET,
    "MOSTLY CLEAN": TEXT_MUTED,
    "CLEAN": SUCCESS,
}


def parse_severity_key(content: str) -> tuple[str, str, str]:
    head = content[:600]
    if "CRITICAL" in head:        return "CRITICAL", t("critical"), SEV_COLOR["CRITICAL"]
    if "NEEDS REVIEW" in head:    return "NEEDS REVIEW", t("needs_review"), SEV_COLOR["NEEDS REVIEW"]
    if "MINOR ISSUES" in head:    return "MINOR", t("minor"), SEV_COLOR["MINOR"]
    if "MOSTLY CLEAN" in head:    return "MOSTLY CLEAN", t("mostly_clean"), SEV_COLOR["MOSTLY CLEAN"]
    return "CLEAN", t("clean"), SEV_COLOR["CLEAN"]


report_data = []
for f in reports:
    content = f.read_text(encoding="utf-8")
    month_match = re.search(r"anomaly_report_(\d{4}-\d{2})", f.name)
    month = month_match.group(1) if month_match else f.name
    sev_key, sev_label, color = parse_severity_key(content)
    report_data.append({"month": month, "key": sev_key, "label": sev_label,
                        "color": color, "file": f, "content": content})


# ─── KPI strip ─────────────────────────────────────────────
counts = {k: 0 for k in SEV_COLOR}
for r in report_data:
    counts[r["key"]] += 1

st.markdown(f"#### {t('severity_summary')}")
c1, c2, c3, c4, c5 = st.columns(5)
with c1: kpi_tile(str(counts["CRITICAL"]),    t("critical"),     accent_color=DANGER)
with c2: kpi_tile(str(counts["NEEDS REVIEW"]), t("needs_review"), accent_color=WARN)
with c3: kpi_tile(str(counts["MINOR"]),        t("minor"),        accent_color=ACCENT_VIOLET)
with c4: kpi_tile(str(counts["MOSTLY CLEAN"]), t("mostly_clean"), accent_color=TEXT_MUTED)
with c5: kpi_tile(str(counts["CLEAN"]),        t("clean"),        accent_color=SUCCESS)


st.caption(f"📊 {len(report_data)} months scanned · {counts['CRITICAL']} critical · "
            f"{counts['NEEDS REVIEW']} needs review · {counts['CLEAN']+counts['MOSTLY CLEAN']} clean")


# ─── Filter + list ─────────────────────────────────────────
st.markdown("---")
st.markdown(f"### {t('all_reports')}")

filter_options = [t("critical"), t("needs_review"), t("minor"), t("mostly_clean"), t("clean")]
default_filter = [t("critical"), t("needs_review"), t("minor")]
sev_filter = st.multiselect(t("filter_severity"), options=filter_options, default=default_filter)

sev_order = {"CRITICAL": 0, "NEEDS REVIEW": 1, "MINOR": 2, "MOSTLY CLEAN": 3, "CLEAN": 4}
report_data.sort(key=lambda r: (sev_order[r["key"]], r["month"]))

filtered = [r for r in report_data if r["label"] in sev_filter]

if not filtered:
    st.info(t("no_match_filter"))
else:
    for r in filtered:
        with st.expander(f"**{r['month']}** · {r['label']}"):
            col1, col2 = st.columns([6, 1])
            with col1:
                st.caption(f"📄 `{r['file'].name}`")
            with col2:
                try:
                    pdf_bytes = markdown_to_pdf(
                        r["content"],
                        f"Anomaly Report · {r['month']}",
                        f"{r['label']} · {datetime.now().strftime('%d %b %Y')}",
                    )
                    st.download_button(
                        t("download_pdf"), data=pdf_bytes,
                        file_name=r["file"].name.replace(".md", ".pdf"),
                        mime="application/pdf", key=f"pdf_{r['month']}",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.button("PDF err", key=f"pdf_err_{r['month']}",
                              disabled=True, use_container_width=True)
            st.markdown(
                f'<div style="background:{BG_PANEL}; border:1px solid {BORDER}; '
                f'border-left:4px solid {r["color"]}; padding:1.5rem; border-radius:8px;">',
                unsafe_allow_html=True,
            )
            st.markdown(r["content"])
            st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")
brand_bar(t("brand_bar_anomaly"))
