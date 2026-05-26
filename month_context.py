"""Compute calendar / operational context for a target month.

The dashboard and AI scripts need to know:
- Is the target month still in progress (data is partial)?
- Which line items are typically only posted at month-end and may legitimately
  show ₹0 in a partial month?

Without this, the LLM compares a partial month to a full prior month and produces
misleading insights ("salary down 100%! profit down 50%!" when really it's just
data that hasn't landed yet).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable

from pnl_reader import MonthlyPnL

# Lines that are typically posted once per month, at month-end.
# If these are ₹0 in a partial month while historical avg is non-zero,
# we treat them as "unposted, not absent".
MONTH_END_POSTED_LINES = ("salary", "electricity", "mandir", "diesel")

# Lines that accrue continuously and should not be flagged as month-end-only.
DAILY_ACCRUING_LINES = ("ultra_rev", "premium_rev", "grocery", "paytm", "misc", "repair")


@dataclass
class MonthContext:
    target_label: str            # e.g. "May 2026"
    target_year: int
    target_month: int
    today: date
    is_current_calendar_month: bool   # True if target month == today's month
    days_in_month: int                # e.g. 31
    days_elapsed: int                 # day-of-month if current calendar month, else days_in_month
    completeness_pct: float           # days_elapsed / days_in_month
    is_partial: bool                  # completeness_pct < 0.95 AND current calendar month
    unposted_lines: list[str] = field(default_factory=list)   # month-end lines that look unposted
    pace_factor: float = 1.0          # multiplier to project partial → full month (full_month_est = partial * pace_factor)

    def to_brief_dict(self) -> dict:
        return {
            "label": self.target_label,
            "today": self.today.isoformat(),
            "is_partial": self.is_partial,
            "days_elapsed": self.days_elapsed,
            "days_in_month": self.days_in_month,
            "completeness_pct": round(self.completeness_pct * 100, 1),
            "unposted_lines": self.unposted_lines,
            "pace_factor": round(self.pace_factor, 3),
        }


def compute_context(
    target: MonthlyPnL,
    history: Iterable[MonthlyPnL],
    today: date | None = None,
) -> MonthContext:
    """Return a MonthContext describing how complete `target` is and which
    expense lines look unposted compared to history."""
    today = today or date.today()
    ty, tm = target.month.year, target.month.month
    days_in_month = calendar.monthrange(ty, tm)[1]
    is_current_calendar_month = (today.year, today.month) == (ty, tm)
    if is_current_calendar_month:
        days_elapsed = min(today.day, days_in_month)
    else:
        # Target is in the past — assume complete.
        days_elapsed = days_in_month
    completeness = days_elapsed / days_in_month
    is_partial = is_current_calendar_month and completeness < 0.95
    pace_factor = (days_in_month / days_elapsed) if days_elapsed > 0 else 1.0

    # Detect month-end lines that look unposted in a partial month.
    unposted: list[str] = []
    if is_partial:
        hist = list(history)
        for line in MONTH_END_POSTED_LINES:
            current = getattr(target, line, 0.0) or 0.0
            if current > 0:
                continue
            # Was this line typically non-zero in prior months?
            prior_vals = [getattr(m, line, 0.0) or 0.0 for m in hist if m is not target]
            non_zero_prior = [v for v in prior_vals if v > 0]
            if non_zero_prior and len(non_zero_prior) >= max(1, len(prior_vals) // 2):
                unposted.append(line)

    return MonthContext(
        target_label=target.label,
        target_year=ty,
        target_month=tm,
        today=today,
        is_current_calendar_month=is_current_calendar_month,
        days_in_month=days_in_month,
        days_elapsed=days_elapsed,
        completeness_pct=completeness,
        is_partial=is_partial,
        unposted_lines=unposted,
        pace_factor=pace_factor,
    )


def render_context_block(ctx: MonthContext) -> str:
    """Plain-text block to drop into an LLM prompt — explains the operational
    state of the month so the model frames insights correctly."""
    if not ctx.is_partial:
        return (
            f"MONTH STATUS\n"
            f"- Target month {ctx.target_label} is COMPLETE (full {ctx.days_in_month} days of data).\n"
            f"- Standard MoM comparisons are valid.\n"
        )

    lines = [
        "MONTH STATUS — PARTIAL MONTH (CRITICAL CONTEXT)",
        f"- Target month {ctx.target_label} is IN PROGRESS as of {ctx.today.isoformat()}.",
        f"- Only {ctx.days_elapsed} of {ctx.days_in_month} days have elapsed "
        f"({ctx.completeness_pct*100:.0f}% of the month).",
        "- DO NOT compute or report month-over-month % changes on totals — the comparison",
        "  is misleading. A 50% drop in revenue may just mean the month is half-over.",
        "- For revenue lines you may say things like 'on pace for X if linear', citing the",
        f"  pace factor of {ctx.pace_factor:.2f}x (i.e. extrapolated full-month estimate).",
        "- DO NOT call this a 'decline' or 'drop' versus prior month.",
    ]
    if ctx.unposted_lines:
        names = ", ".join(ctx.unposted_lines)
        lines.append(
            f"- These expense lines are typically posted at month-end and currently show ₹0:"
        )
        lines.append(
            f"    {names}"
        )
        lines.append(
            "  Treat them as UNPOSTED, not absent. Do not flag them green/positive. Do not"
        )
        lines.append(
            "  claim 'no payroll' or 'no utility costs' — say 'salary/electricity not yet"
        )
        lines.append(
            "  posted (typical month-end entry)' instead."
        )
    lines.append(
        "- Profit and total-expense MoM deltas are unreliable for this month — flag the"
    )
    lines.append(
        "  partial-month caveat prominently in 'Headline' and again in 'Worth checking'."
    )
    return "\n".join(lines) + "\n"


__all__ = ["MonthContext", "compute_context", "render_context_block",
           "MONTH_END_POSTED_LINES", "DAILY_ACCRUING_LINES"]
