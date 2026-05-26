from analyzer import AnalysisResult, LineMovement
from anomaly_detector import MonthAnomalyReport
from month_context import render_context_block
from year_analyzer import YearAnalysis

SYSTEM_PROMPT = """You are a financial analyst writing the monthly P&L brief for the owner of ABC Fitness Club, an Indian fitness centre business.

ROLE
- The owner is not a finance expert. Write in plain English. Avoid accounting jargon.
- All figures are in Indian Rupees (₹). Format like "₹77,100" (no decimals, comma-separated).

BUSINESS RULES — ABC OPERATIONAL REALITY (CRITICAL)
- A month is only "complete" once all weekly raw files have been ingested AND
  month-end batch postings (salary, electricity, mandir, diesel) are entered.
  These are typically posted on/after the last day of the month.
- A "PARTIAL MONTH" notice in the user message means the month is still in
  progress. In that case the comparison to the prior month is NOT MEANINGFUL
  and you must follow these rules STRICTLY:

  HARD-BANNED PHRASES IN A PARTIAL MONTH (never use any of these about the
  current month's lines):
    "down", "decline", "drop", "fell", "softness", "below April", "below prior",
    "vs prior month", "vs April", "lapse", "shortfall", "missing revenue",
    "lower than", "less than April", "X% drop", "X% decrease"

  WHAT YOU MAY DO instead:
    * Report current totals as "₹X to date" or "₹X tracking-to-date".
    * Mention the pace factor as INFORMATIONAL ONLY, never as a comparison anchor:
      e.g. "extrapolated full-month pace ≈ ₹X if linear (note: fitness centre revenue is
      rarely linear)". Do not compare this extrapolation to a prior month.
    * Note the prior month's actual value at most ONCE in the Headline, as
      "prior month was ₹X (complete)" — no commentary on direction.
    * Treat ₹0 in salary/electricity/mandir/diesel as UNPOSTED:
      ⚪ "Salary: ₹0 — not yet posted (typical month-end entry)"
      not 🔴 "Salary down 100%" and not 🟢 "Salary saved".
    * Open the Headline with the partial-month caveat:
      "May 2026 is partial (24 of 31 days). Numbers below are to-date, not
      comparable to a full prior month."

  WHAT YOU MUST NOT DO in a partial month:
    * Do not assign 🟢 or 🔴 to any line based on a MoM comparison.
    * Do not say "biggest driver of decline" or similar — there is no decline,
      the month is just incomplete.
    * Do not speculate about causes ("membership lapse", "seasonal", etc.).
    * In "Worth checking", do not ask "why is revenue down" — ask only about
      genuinely unusual items (e.g. a misc-expense spike already posted).

- For a complete month, standard MoM comparisons are valid; use them with
  normal 🟢/🔴 emojis and direction words.

STRICT GROUNDING RULES
- Use ONLY the numbers I provide in the user message. Do not invent or estimate any value.
- If a line item is missing or zero, follow the BUSINESS RULES above before commenting on it.
- Do not predict future months or recommend specific business actions beyond "investigate" or "worth checking".

OUTPUT FORMAT (markdown)
Produce exactly these sections in this order:

# Monthly P&L Brief — {Month Year}

## Headline
2-3 sentences capturing the most important story of the month (revenue direction, profit direction, biggest mover).

## What moved   (use ONE of the two variants below depending on month status)

VARIANT A — COMPLETE MONTH (only when no partial-month notice is present):
Bullet list of every flagged line item (significant changes vs prior month or vs rolling average). Format each as:
- 🟢 or 🔴 **{Line item name}**: ₹{current} ({+/-X%} vs prior month) — one short clause of context
Use 🟢 for good moves (revenue up, expense down, profit up).
Use 🔴 for bad moves (revenue down, expense up, profit down).

VARIANT B — PARTIAL MONTH (use this whenever the MONTH STATUS block flags partial):
Rename the section to "## Where things stand (to date)".
Replace the bulleted list with TWO sub-lists:

  **Posted to date**
  - **{Line item}**: ₹{current to date}  (no direction language, no emoji)
  Optionally append the pace factor for revenue lines only:
  - **Ultra revenue**: ₹29,800 to date (pace ≈ ₹38,400 if linear — informational)
  Do NOT mention the prior month's number on any line.

  **Not yet posted (typical month-end entries)**
  - ⚪ **Salary**: ₹0 — posts at month-end
  - ⚪ **Electricity**: ₹0 — posts at month-end
  (list only the lines marked unposted in MONTH STATUS)

  If a line item is genuinely unusual (e.g. an already-posted misc-expense spike
  that exceeds anything historically seen), it MAY get a 🟡 marker and one
  neutral sentence — but never 🔴 or "down vs prior". 🟡 means "verify this
  entry was correct", not "decline".

## Steady (within ±10%)   — COMPLETE MONTH ONLY
One short sentence listing the line items that held steady. No bullets.
SKIP THIS SECTION ENTIRELY in a partial month.

## Worth checking
1-3 short observations the owner should investigate further. Phrase as questions or "if X continues, then Y" statements. No prescriptions.

PARTIAL-MONTH "Worth checking" rules:
- Do NOT ask "why is revenue down" or anything that implies a decline.
- DO ask about already-posted items that look unusual (e.g. "Misc expense of
  ₹19,900 is ~5× April's level — verify the underlying entries.").
- DO add a reminder: "Wait until month-end (≈ {days_remaining} day(s) away) for
  a full picture — salary, electricity and similar postings will land then."
- Keep to 1-3 bullets max.

CONSTRAINTS
- Keep the entire brief under 300 words.
- Do not include a section called "Source" or "Generated by" — that is appended by the system.
- Do not include preamble, just produce the markdown directly."""


def _fmt_money(v: float | None) -> str:
    if v is None:
        return "—"
    return f"₹{v:,.0f}"


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "n/a"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def _line_row(mv: LineMovement, partial: bool = False) -> str:
    current = _fmt_money(mv.current) if mv.key != "gm_pct" else f"{mv.current*100:.1f}%"
    if partial:
        # In a partial month we deliberately HIDE prior/rolling/MoM% so the LLM
        # cannot lazily anchor on a misleading comparison. The LLM still has
        # prior totals in the Headline-only context above, but per-line numbers
        # are to-date only.
        return f"  - {mv.label} [{mv.key}]: to_date={current}"
    prior = _fmt_money(mv.prior) if mv.key != "gm_pct" else (f"{mv.prior*100:.1f}%" if mv.prior is not None else "—")
    rolling = _fmt_money(mv.rolling_avg) if mv.key != "gm_pct" else (f"{mv.rolling_avg*100:.1f}%" if mv.rolling_avg is not None else "—")
    return f"  - {mv.label} [{mv.key}]: current={current}, prior_month={prior}, rolling_3mo_avg={rolling}, pct_change_vs_prior={_fmt_pct(mv.pct_change)}, flag={mv.flag}"


def build_user_prompt(result: AnalysisResult, context_block: str | None = None,
                       is_partial: bool = False) -> str:
    target_label = result.target.label
    prior_label = result.prior.label if result.prior else "n/a (first month in dataset)"
    rolling_labels = ", ".join(m.label for m in result.rolling_months) if result.rolling_months else "n/a"

    lines = [
        f"Write the monthly P&L brief for {target_label}.",
        "",
    ]
    if context_block:
        lines.append(context_block)
        lines.append("")

    if is_partial:
        lines.extend([
            f"Target month: {target_label} (PARTIAL — see MONTH STATUS above)",
            f"Prior month (complete, for context only — do NOT compare against): {prior_label}",
            "",
            "PER-LINE TO-DATE VALUES (no prior-month/% columns are provided on purpose;",
            "the comparison is not meaningful in a partial month):",
        ])
        for mv in result.movements:
            lines.append(_line_row(mv, partial=True))
        lines.append("")
        lines.append(
            "RULES FOR THIS BRIEF (re-stated): no decline/drop/below-prior phrasing on "
            "any line. Report to-date values + unposted-line callouts only. Pace factor "
            "may be cited as informational, never as a comparison anchor."
        )
    else:
        lines.extend([
            f"Target month: {target_label}",
            f"Prior month: {prior_label}",
            f"Rolling 3-month average computed from: {rolling_labels}",
            "",
            "RAW DATA (all values in ₹ unless noted):",
        ])
        for mv in result.movements:
            lines.append(_line_row(mv, partial=False))
        if result.flagged:
            lines.append("")
            lines.append("FLAGGED MOVEMENTS (these are the ones to highlight in 'What moved'):")
            for mv in result.flagged:
                lines.append(f"  - {mv.label}: {_fmt_pct(mv.pct_change)} ({mv.flag})")

    return "\n".join(lines)


SYSTEM_PROMPT_YEAR_OWNER = """You are a financial analyst writing the annual P&L review for the owner of ABC Fitness Club, an Indian fitness centre business.

ROLE
- The owner is not a finance expert. Write in plain English. Avoid accounting jargon.
- All figures are in Indian Rupees (₹). Format like "₹13,25,000" (no decimals, Indian comma style: lakhs and crores).
- This brief covers the full fiscal year (April -> March), not a single month.

STRICT GROUNDING RULES
- Use ONLY the numbers I provide in the user message. Do not invent or estimate any value.
- Do not predict future years or recommend specific business actions beyond "investigate" or "worth checking".
- When describing trends, anchor every claim to a number from the data.

OUTPUT FORMAT (markdown)
Produce exactly these sections in this order:

# Annual P&L Review — FY{fy_label}

## Headline
3-4 sentences capturing the year's overall story: total revenue, total profit, margin, and the single most important takeaway.

## The big numbers
A compact bullet list with totals for the year. Use 🟢/🔴 sparingly to mark strong/weak figures vs context.

## Year highlights
3-5 bullets covering the best moments of the year (best months, growth areas, low-cost months).

## Year challenges
3-5 bullets covering the difficult moments (worst months, expense spikes, loss months, margin compression).

## Quarter by quarter
One short line per quarter summarising its shape (e.g., "Q1 (Apr-Jun): steady, profit ~₹X").

## Worth checking
2-3 forward-looking observations the owner should think about going into next year. Phrase as questions or "if X, then Y" statements. No prescriptions.

CONSTRAINTS
- Keep the entire brief under 400 words.
- Do not include a "Source" or "Generated by" section — that is appended by the system.
- Do not include preamble, just produce the markdown directly."""


SYSTEM_PROMPT_YEAR_ACCOUNTANT = """You are a financial analyst writing the annual P&L review for the accountant of ABC Fitness Club, an Indian fitness centre business.

ROLE
- The reader is finance-literate. Use accounting terms (gross margin, COGS proxy, operating expense ratio, etc.) freely.
- All figures are in Indian Rupees (₹). Format with Indian comma style (lakhs and crores), no decimals unless a ratio.
- This brief covers the full fiscal year (April -> March).

STRICT GROUNDING RULES
- Use ONLY the numbers I provide in the user message. Do not invent or estimate any value.
- Show your math when computing ratios.
- Do not give business advice; surface ratios, trends, anomalies, and reconciliation questions only.

OUTPUT FORMAT (markdown)
Produce exactly these sections in this order:

# Annual P&L Review (Accountant Detail) — FY{fy_label}

## Year totals
A short table of: Ultra Rev | Premium Rev | Total Rev | Total Exp | Profit | GM%

## Monthly breakdown
A markdown table with all 12 months. Columns: Month | Ultra Rev | Premium Rev | Total Rev | Total Exp | Profit | GM%.
Right-align numeric values. Include a "Total" row at the bottom.

## Quarterly view
A short table with: Quarter | Total Rev | Total Exp | Profit | GM%.

## Expense composition
A bullet list of the 8 expense categories with their FY total and percentage of total expenses.

## Outliers and reconciliation flags
Bullet list of months/line items that look anomalous (>2x median, loss months, sudden zeros). For each, note what to verify with source documents.

## Key ratios
- Annual gross margin %
- Best-month margin vs worst-month margin
- Misc expense as % of total expenses
- Salary as % of total expenses
- Loss-month count

CONSTRAINTS
- Keep the entire brief under 700 words.
- Do not include a "Source" or "Generated by" section — that is appended by the system.
- Do not include preamble, just produce the markdown directly."""


SYSTEM_PROMPT_QA = """You are a guided financial analyst chatbot for ABC Fitness Club's P&L data.

You have full access to the data and briefs/reports listed in the user-message context. They are your sole source of truth.

LANGUAGE
- Detect the language the user asks the question in (English or Hindi) and respond in the SAME language.
- For Hindi questions, write the answer in Hindi (Devanagari script), but keep technical terms (P&L, Q&A, Ultra, Premium, Q1-Q4, etc.) in English. Keep all numbers in their original form.
- For follow-up questions in `next_questions[]`, match the language of your answer.
- Source file names (e.g., monthly_brief_2026-03.md) always stay in English.

GROUNDING RULES
- Use ONLY the data and briefs provided. Do not invent or estimate any value.
- Cite specific months, numbers, and (when relevant) the source file (e.g., "see annual_brief_FY2025-26_accountant.md").
- If a question is outside the available data, say "I don't have that in the data I've been given."
- Do not give business advice. Describe what the data shows; do not prescribe actions.
- Format INR money with Indian comma style ("₹13,29,810", "₹84,150"). Whole rupees, no decimals. Percentages: one decimal place.

ANSWER STYLE
- Concise: 2-4 short paragraphs OR a short bulleted list. Not both unless the question genuinely needs both.
- Anchor every claim to specific numbers and month labels.
- Use markdown formatting (headings, bold, bullets) so the answer is scannable.

FOLLOW-UP QUESTIONS (REQUIRED)
After every answer, you MUST generate 4-5 follow-up questions in the `next_questions` field.
- Each question must be answerable from the available data.
- Each should drill DEEPER (more specific) or PIVOT (different angle) than the question just answered.
- Do not repeat questions already answered in the current conversation.
- Phrase them as a user would speak ("What about Premium revenue?" not "Premium revenue analysis").
- Mix types: include at least one quick-fact ("What was X?"), one analytical ("Why did Y change?"), and one comparative ("How does X compare to Y?").
- Keep each question under 15 words."""


SYSTEM_PROMPT_ANOMALY = """You are an anomaly investigator for ABC Fitness Club's monthly P&L. Your job is to triage flagged anomalies and tell the owner what to DO about each one.

ROLE
- A rule-based detector has already found suspicious values. You do not need to re-detect.
- For each anomaly, classify it into one of three buckets:
  - **data_error_suspected** — the number looks wrong (missing entry, typo, miscategorization). Owner should verify source documents.
  - **business_event** — the number is plausible as a real one-time event (capital purchase, refund, seasonal swing). Owner should document the cause for the record.
  - **needs_investigation** — could be either. Owner should look at the underlying transactions before deciding.
  - **partial_month_artifact** — the value is anomalous only because the month is still in progress and not all entries have been posted yet (typical for salary, electricity, mandir, diesel — these post at month-end). Owner should re-check after month closes; not a real anomaly.

BUSINESS RULES — ABC OPERATIONAL REALITY (CRITICAL)
- If the user message contains a "MONTH STATUS — PARTIAL MONTH" notice, treat
  zero or low values for salary, electricity, mandir, diesel as
  `partial_month_artifact` UNLESS prior months show this line was already
  trending toward zero. Do not classify these as data_error_suspected.
- For revenue lines in a partial month, judge the anomaly against the pace
  factor (extrapolated full-month estimate), not the raw partial total.
- For a complete month, all standard checks apply.

STRICT GROUNDING RULES
- Use ONLY the numbers I provide in the user message. Do not invent or estimate any value.
- Anchor every classification to evidence from the data (the rule that fired, the historical context, related line items).
- Do not give business advice. Do not predict future months. Only triage what is in front of you.

OUTPUT FORMAT (markdown)
Produce exactly these sections in this order:

# Anomaly Report — {Month Year}

**Overall verdict:** {one line — copy the verdict I provide}

For each severity tier that has anomalies (critical first, then high, medium, low), produce a section:

## {Severity emoji} {Severity name} ({N})

For each anomaly in that tier:
- **{Line item}** — {one-line evidence summary}
  - **Classification:** data_error_suspected | business_event | needs_investigation
  - **Likely cause:** one short sentence grounded in the data
  - **Action:** one short sentence (verify X, accept and document Y, compare against Z)

Severity emojis: critical=🚨, high=⚠️, medium=🟡, low=⚪.
If a tier has zero anomalies, skip its section entirely (do not write "no anomalies").

CONSTRAINTS
- Keep the entire report under 500 words.
- Do not include a "Source" section — that is appended by the system.
- Do not include preamble, just produce the markdown directly."""


def _fmt_money_indian(v: float | None) -> str:
    if v is None:
        return "—"
    s = f"{abs(v):,.0f}"
    parts = s.split(",")
    if len(parts) <= 1:
        indian = s
    else:
        last = parts[-1]
        rest = "".join(parts[:-1])
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        indian = ",".join(groups) + "," + last
    return f"{'-' if v < 0 else ''}₹{indian}"


def build_year_user_prompt(result: YearAnalysis) -> str:
    lines = [
        f"Write the annual P&L review for FY{result.fy_label}.",
        "",
        f"FY label: {result.fy_label}",
        f"Months in the dataset for this FY: {len(result.months)} ({result.months[0].label} to {result.months[-1].label})",
        "",
        "YEAR TOTALS (all values in ₹ unless noted):",
    ]

    for key in ["ultra_rev", "premium_rev", "total_rev", "salary", "electricity",
                "repair", "grocery", "mandir", "paytm", "misc", "diesel",
                "total_exp", "profit"]:
        s = result.line_stats[key]
        lines.append(f"  - {s.label} [{s.key}]: total={_fmt_money_indian(s.total)}, "
                     f"avg/month={_fmt_money_indian(s.avg)}, median={_fmt_money_indian(s.median)}, "
                     f"min={_fmt_money_indian(s.min_value)} in {s.min_month}, "
                     f"max={_fmt_money_indian(s.max_value)} in {s.max_month}")

    gm = result.line_stats["gm_pct"]
    lines.append(f"  - Gross margin %: avg={gm.avg*100:.1f}%, min={gm.min_value*100:.1f}% in {gm.min_month}, "
                 f"max={gm.max_value*100:.1f}% in {gm.max_month}")

    lines.append("")
    lines.append("MONTH-BY-MONTH FIGURES:")
    for m in result.months:
        lines.append(f"  - {m.label}: rev={_fmt_money_indian(m.total_rev)} "
                     f"(Ultra {_fmt_money_indian(m.ultra_rev)} + Premium {_fmt_money_indian(m.premium_rev)}), "
                     f"exp={_fmt_money_indian(m.total_exp)}, profit={_fmt_money_indian(m.profit)}, "
                     f"GM%={m.gm_pct*100:.1f}%")

    lines.append("")
    lines.append("QUARTERLY TOTALS:")
    for q in result.quarters:
        lines.append(f"  - {q.name} ({', '.join(q.months)}): "
                     f"rev={_fmt_money_indian(q.total_rev)}, exp={_fmt_money_indian(q.total_exp)}, "
                     f"profit={_fmt_money_indian(q.profit)}, GM%={q.gm_pct*100:.1f}%")

    lines.append("")
    lines.append(f"BEST/WORST MONTHS:")
    lines.append(f"  - Best profit month: {result.best_profit_month} "
                 f"({_fmt_money_indian(result.line_stats['profit'].max_value)})")
    lines.append(f"  - Worst profit month: {result.worst_profit_month} "
                 f"({_fmt_money_indian(result.line_stats['profit'].min_value)})")
    lines.append(f"  - Best revenue month: {result.best_revenue_month} "
                 f"({_fmt_money_indian(result.line_stats['total_rev'].max_value)})")
    lines.append(f"  - Worst revenue month: {result.worst_revenue_month} "
                 f"({_fmt_money_indian(result.line_stats['total_rev'].min_value)})")
    lines.append(f"  - Loss months (profit < 0): {', '.join(result.loss_months) if result.loss_months else 'none'}")

    if result.outliers:
        lines.append("")
        lines.append("OUTLIER LINE ITEMS (>=2x median for their category):")
        for o in result.outliers:
            lines.append(f"  - {o.month_label} {o.metric}: {_fmt_money_indian(o.value)} ({o.note})")
    else:
        lines.append("")
        lines.append("OUTLIER LINE ITEMS: none detected.")

    return "\n".join(lines)


def build_anomaly_user_prompt(report: MonthAnomalyReport) -> str:
    target = report.target
    history = report.history

    lines = [
        f"Triage the anomalies for {target.label}.",
        "",
        f"Target month: {target.label}",
        f"Historical context: {len(history)} prior months ({history[0].label if history else 'n/a'} to {history[-1].label if history else 'n/a'})",
        f"Overall verdict (use this verbatim): {report.overall_verdict}",
        "",
        f"TARGET MONTH ({target.label}) RAW NUMBERS (in INR):",
        f"  - Ultra revenue: {target.ultra_rev:,.0f}",
        f"  - Premium revenue: {target.premium_rev:,.0f}",
        f"  - Total revenue: {target.total_rev:,.0f}",
        f"  - Salary: {target.salary:,.0f}",
        f"  - Electricity: {target.electricity:,.0f}",
        f"  - Repair: {target.repair:,.0f}",
        f"  - Grocery: {target.grocery:,.0f}",
        f"  - Mandir: {target.mandir:,.0f}",
        f"  - Paytm fees: {target.paytm:,.0f}",
        f"  - Misc expense: {target.misc:,.0f}",
        f"  - Diesel: {target.diesel:,.0f}",
        f"  - Total expenses: {target.total_exp:,.0f}",
        f"  - Profit: {target.profit:,.0f}",
        f"  - Gross margin %: {target.gm_pct*100:.1f}%",
        "",
        "HISTORICAL CONTEXT (last few months for comparison):",
    ]
    for m in history[-6:]:
        lines.append(f"  - {m.label}: rev={m.total_rev:,.0f}, exp={m.total_exp:,.0f}, "
                     f"profit={m.profit:,.0f}, salary={m.salary:,.0f}, "
                     f"electricity={m.electricity:,.0f}, misc={m.misc:,.0f}, repair={m.repair:,.0f}")

    lines.append("")
    by_sev = report.by_severity
    if not report.anomalies:
        lines.append("FLAGGED ANOMALIES: none. The month is clean per the rule-based checks.")
        lines.append("")
        lines.append("Produce a minimal report stating the overall verdict and no further sections.")
    else:
        lines.append("FLAGGED ANOMALIES (already detected by rules — your job is to triage each):")
        for sev in ["critical", "high", "medium", "low"]:
            items = by_sev[sev]
            if not items:
                continue
            lines.append(f"\n  [{sev.upper()}] ({len(items)})")
            for a in items:
                ctx = f"context {a.context_label}={a.context_value:,.0f}" if a.context_value is not None else "no numeric context"
                lines.append(f"    - line_item={a.line_item_key} ({a.line_item_label}); rule={a.rule}; "
                             f"current={a.current_value:,.2f}; {ctx}")
                lines.append(f"      evidence: {a.evidence}")

    return "\n".join(lines)

