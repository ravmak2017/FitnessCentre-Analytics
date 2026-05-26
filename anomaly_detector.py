from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Literal

from analyzer import EXPENSE_KEYS, LABELS
from pnl_reader import MonthlyPnL

Severity = Literal["low", "medium", "high", "critical"]


@dataclass
class Anomaly:
    month_label: str
    line_item_key: str
    line_item_label: str
    rule: str
    current_value: float
    context_value: float | None
    context_label: str
    severity: Severity
    evidence: str


@dataclass
class MonthAnomalyReport:
    target: MonthlyPnL
    history: list[MonthlyPnL]
    anomalies: list[Anomaly]

    @property
    def by_severity(self) -> dict[Severity, list[Anomaly]]:
        out: dict[Severity, list[Anomaly]] = {"critical": [], "high": [], "medium": [], "low": []}
        for a in self.anomalies:
            out[a.severity].append(a)
        return out

    @property
    def overall_verdict(self) -> str:
        s = self.by_severity
        if s["critical"]:
            return "CRITICAL — at least one finding requires immediate attention"
        if s["high"]:
            return "NEEDS REVIEW — high-severity finding(s) detected"
        if s["medium"]:
            return "MINOR ISSUES — some items worth investigating"
        if s["low"]:
            return "MOSTLY CLEAN — only low-severity items"
        return "CLEAN — no anomalies detected"


def _val(m: MonthlyPnL, key: str) -> float:
    return getattr(m, key)


def _z_score(value: float, values: list[float]) -> float | None:
    if len(values) < 3:
        return None
    mu = mean(values)
    sigma = pstdev(values)
    if sigma == 0:
        return None
    return (value - mu) / sigma


def detect(target: MonthlyPnL, history: list[MonthlyPnL]) -> list[Anomaly]:
    """Run rule-based anomaly detection on a target month vs historical context."""
    if not history:
        return []

    anomalies: list[Anomaly] = []
    all_keys_for_z = ["ultra_rev", "premium_rev"] + EXPENSE_KEYS

    if target.profit < 0:
        anomalies.append(Anomaly(
            month_label=target.label,
            line_item_key="profit",
            line_item_label=LABELS["profit"],
            rule="negative_profit",
            current_value=target.profit,
            context_value=None,
            context_label="—",
            severity="critical",
            evidence=f"Profit is negative: revenue INR {target.total_rev:,.0f} minus expenses INR {target.total_exp:,.0f} = loss of INR {abs(target.profit):,.0f}.",
        ))

    trailing = history[-3:] if len(history) >= 3 else history
    trailing_gm_avg = mean(m.gm_pct for m in trailing) if trailing else 0.0
    gm_drop = (trailing_gm_avg - target.gm_pct) * 100
    if gm_drop >= 15:
        anomalies.append(Anomaly(
            month_label=target.label,
            line_item_key="gm_pct",
            line_item_label=LABELS["gm_pct"],
            rule="gm_collapse",
            current_value=target.gm_pct,
            context_value=trailing_gm_avg,
            context_label=f"trailing {len(trailing)}-mo avg",
            severity="high" if gm_drop >= 25 else "medium",
            evidence=f"Gross margin {target.gm_pct*100:.1f}% vs trailing {len(trailing)}-mo average of {trailing_gm_avg*100:.1f}% (drop of {gm_drop:.1f} percentage points).",
        ))

    for key in ["ultra_rev", "premium_rev"]:
        if not history:
            continue
        prior = history[-1]
        prior_val = _val(prior, key)
        current_val = _val(target, key)
        if prior_val <= 0:
            continue
        drop_pct = (prior_val - current_val) / prior_val * 100
        if drop_pct >= 30:
            anomalies.append(Anomaly(
                month_label=target.label,
                line_item_key=key,
                line_item_label=LABELS[key],
                rule="revenue_collapse",
                current_value=current_val,
                context_value=prior_val,
                context_label=f"prior month ({prior.label})",
                severity="high" if drop_pct >= 50 else "medium",
                evidence=f"{LABELS[key]} fell {drop_pct:.1f}% from INR {prior_val:,.0f} to INR {current_val:,.0f}.",
            ))

    for key in all_keys_for_z:
        history_vals = [_val(m, key) for m in history]
        current_val = _val(target, key)
        if all(v == 0 for v in history_vals) and current_val == 0:
            continue
        non_zero_history = sum(1 for v in history_vals if v > 0)

        if current_val == 0 and non_zero_history >= 3 and len(history) >= 3:
            last_three = history_vals[-3:]
            if all(v > 0 for v in last_three):
                avg_last_three = mean(last_three)
                if avg_last_three > 1000:
                    anomalies.append(Anomaly(
                        month_label=target.label,
                        line_item_key=key,
                        line_item_label=LABELS[key],
                        rule="unexpected_zero",
                        current_value=0.0,
                        context_value=avg_last_three,
                        context_label="avg of last 3 months",
                        severity="high",
                        evidence=f"{LABELS[key]} is zero this month, but averaged INR {avg_last_three:,.0f} across the last 3 months ({', '.join(m.label for m in history[-3:])}).",
                    ))

        zero_history = sum(1 for v in history_vals if v == 0)
        if (current_val >= 5000 and zero_history >= max(3, len(history_vals) - 2)
                and current_val > 0):
            anomalies.append(Anomaly(
                month_label=target.label,
                line_item_key=key,
                line_item_label=LABELS[key],
                rule="new_spike",
                current_value=current_val,
                context_value=0.0,
                context_label=f"{zero_history} of {len(history_vals)} prior months were zero",
                severity="medium" if current_val < 20000 else "high",
                evidence=f"{LABELS[key]} is INR {current_val:,.0f} this month; was zero in {zero_history} of the {len(history_vals)} prior months.",
            ))

        z = _z_score(current_val, history_vals)
        if z is not None and abs(z) >= 2:
            already = any(a.line_item_key == key and a.month_label == target.label for a in anomalies)
            if not already:
                hist_avg = mean(history_vals)
                severity: Severity = "high" if abs(z) >= 3 else "medium" if abs(z) >= 2.5 else "low"
                anomalies.append(Anomaly(
                    month_label=target.label,
                    line_item_key=key,
                    line_item_label=LABELS[key],
                    rule="z_score_outlier",
                    current_value=current_val,
                    context_value=hist_avg,
                    context_label=f"historical avg over {len(history_vals)} months",
                    severity=severity,
                    evidence=f"{LABELS[key]} is INR {current_val:,.0f} vs historical avg INR {hist_avg:,.0f} (z-score {z:+.1f}).",
                ))

    return anomalies


def build_report(target: MonthlyPnL, history: list[MonthlyPnL]) -> MonthAnomalyReport:
    anomalies = detect(target, history)
    return MonthAnomalyReport(target=target, history=history, anomalies=anomalies)
