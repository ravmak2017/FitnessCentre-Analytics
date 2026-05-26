from dataclasses import dataclass
from typing import Literal

from pnl_reader import MonthlyPnL, EXPENSE_KEYS

REVENUE_KEYS = ["ultra_rev", "premium_rev", "total_rev"]
DERIVED_KEYS = ["total_exp", "profit", "gm_pct"]
ALL_KEYS = REVENUE_KEYS + EXPENSE_KEYS + DERIVED_KEYS

LABELS = {
    "ultra_rev": "Ultra membership revenue",
    "premium_rev": "Premium membership revenue",
    "total_rev": "Total revenue",
    "salary": "Salary",
    "electricity": "Electricity",
    "repair": "Repair",
    "grocery": "Grocery",
    "mandir": "Mandir",
    "paytm": "Paytm fees",
    "misc": "Misc expense",
    "diesel": "Diesel",
    "total_exp": "Total expenses",
    "profit": "Profit",
    "gm_pct": "Gross margin %",
}

SIGNIFICANT_PCT = 10.0
Flag = Literal["up_significant", "down_significant", "new", "vanished", "steady"]


@dataclass
class LineMovement:
    key: str
    label: str
    current: float
    prior: float | None
    rolling_avg: float | None
    abs_change: float | None
    pct_change: float | None
    flag: Flag


@dataclass
class AnalysisResult:
    target: MonthlyPnL
    prior: MonthlyPnL | None
    rolling_months: list[MonthlyPnL]
    movements: list[LineMovement]

    @property
    def flagged(self) -> list[LineMovement]:
        return [m for m in self.movements if m.flag != "steady"]

    @property
    def steady(self) -> list[LineMovement]:
        return [m for m in self.movements if m.flag == "steady"]


def _val(m: MonthlyPnL, key: str) -> float:
    return getattr(m, key)


def _classify(current: float, prior: float | None, pct: float | None) -> Flag:
    if prior in (None, 0) and current > 0:
        return "new" if prior == 0 else "steady"
    if prior and prior > 0 and current == 0:
        return "vanished"
    if pct is None:
        return "steady"
    if pct >= SIGNIFICANT_PCT:
        return "up_significant"
    if pct <= -SIGNIFICANT_PCT:
        return "down_significant"
    return "steady"


def analyze(months: list[MonthlyPnL], target_month: str | None = None) -> AnalysisResult:
    if not months:
        raise ValueError("No months available for analysis")

    if target_month:
        match = [m for m in months if m.month.strftime("%Y-%m") == target_month]
        if not match:
            raise ValueError(f"Month {target_month} not found in data")
        target = match[0]
    else:
        target = months[-1]

    target_idx = months.index(target)
    prior = months[target_idx - 1] if target_idx > 0 else None
    rolling_months = months[max(0, target_idx - 3):target_idx]

    movements: list[LineMovement] = []
    for key in ALL_KEYS:
        current = _val(target, key)
        prior_val = _val(prior, key) if prior else None
        rolling_avg = (sum(_val(m, key) for m in rolling_months) / len(rolling_months)) if rolling_months else None

        if prior_val is None:
            abs_change = None
            pct = None
        else:
            abs_change = current - prior_val
            pct = ((current - prior_val) / prior_val * 100) if prior_val else None

        movements.append(LineMovement(
            key=key,
            label=LABELS[key],
            current=current,
            prior=prior_val,
            rolling_avg=rolling_avg,
            abs_change=abs_change,
            pct_change=pct,
            flag=_classify(current, prior_val, pct),
        ))

    return AnalysisResult(target=target, prior=prior, rolling_months=rolling_months, movements=movements)
