from dataclasses import dataclass
from datetime import datetime
from statistics import mean, median, pstdev

from analyzer import ALL_KEYS, LABELS
from pnl_reader import MonthlyPnL


@dataclass
class LineStat:
    key: str
    label: str
    total: float
    avg: float
    median: float
    min_value: float
    max_value: float
    min_month: str
    max_month: str


@dataclass
class QuarterStat:
    name: str
    months: list[str]
    total_rev: float
    total_exp: float
    profit: float
    gm_pct: float


@dataclass
class OutlierMonth:
    month_label: str
    metric: str
    value: float
    multiple_of_median: float
    note: str


@dataclass
class YearAnalysis:
    fy_label: str
    months: list[MonthlyPnL]
    line_stats: dict[str, LineStat]
    quarters: list[QuarterStat]
    outliers: list[OutlierMonth]
    loss_months: list[str]
    best_profit_month: str
    worst_profit_month: str
    best_revenue_month: str
    worst_revenue_month: str


def _val(m: MonthlyPnL, key: str) -> float:
    return getattr(m, key)


def _fy_for_month(month: datetime) -> str:
    """FY runs Apr -> Mar. April 2025 onwards = FY2025-26."""
    start_year = month.year if month.month >= 4 else month.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def filter_by_fy(months: list[MonthlyPnL], fy_label: str | None) -> tuple[list[MonthlyPnL], str]:
    if fy_label is None:
        fy_label = _fy_for_month(months[-1].month)
    selected = [m for m in months if _fy_for_month(m.month) == fy_label]
    if not selected:
        raise ValueError(f"No months found for FY{fy_label}")
    return selected, fy_label


def _quarter_for(month_dt: datetime) -> str:
    m = month_dt.month
    if m in (4, 5, 6):
        return "Q1 (Apr-Jun)"
    if m in (7, 8, 9):
        return "Q2 (Jul-Sep)"
    if m in (10, 11, 12):
        return "Q3 (Oct-Dec)"
    return "Q4 (Jan-Mar)"


def analyze_year(all_months: list[MonthlyPnL], fy_label: str | None = None) -> YearAnalysis:
    months, fy_label = filter_by_fy(all_months, fy_label)

    line_stats: dict[str, LineStat] = {}
    for key in ALL_KEYS:
        values = [_val(m, key) for m in months]
        max_idx = values.index(max(values))
        min_idx = values.index(min(values))
        line_stats[key] = LineStat(
            key=key,
            label=LABELS[key],
            total=sum(values),
            avg=mean(values),
            median=median(values),
            min_value=values[min_idx],
            max_value=values[max_idx],
            min_month=months[min_idx].label,
            max_month=months[max_idx].label,
        )

    quarters_dict: dict[str, list[MonthlyPnL]] = {}
    for m in months:
        quarters_dict.setdefault(_quarter_for(m.month), []).append(m)
    quarters: list[QuarterStat] = []
    for name in ["Q1 (Apr-Jun)", "Q2 (Jul-Sep)", "Q3 (Oct-Dec)", "Q4 (Jan-Mar)"]:
        qms = quarters_dict.get(name, [])
        if not qms:
            continue
        rev = sum(m.total_rev for m in qms)
        exp = sum(m.total_exp for m in qms)
        quarters.append(QuarterStat(
            name=name,
            months=[m.label for m in qms],
            total_rev=rev,
            total_exp=exp,
            profit=rev - exp,
            gm_pct=(rev - exp) / rev if rev else 0.0,
        ))

    outliers: list[OutlierMonth] = []
    ABS_FLOOR = 5000
    for key in ["total_exp", "misc", "repair", "ultra_rev", "premium_rev"]:
        med = line_stats[key].median
        avg = line_stats[key].avg
        for m in months:
            v = _val(m, key)
            if med > 0 and v >= med * 2 and v >= med + 1000:
                outliers.append(OutlierMonth(
                    month_label=m.label,
                    metric=LABELS[key],
                    value=v,
                    multiple_of_median=v / med,
                    note=f"{v/med:.1f}x the median ({LABELS[key]} median = INR {med:,.0f})",
                ))
            elif med == 0 and avg > 0 and v >= avg * 2 and v >= ABS_FLOOR:
                outliers.append(OutlierMonth(
                    month_label=m.label,
                    metric=LABELS[key],
                    value=v,
                    multiple_of_median=v / avg,
                    note=f"{v/avg:.1f}x the FY average for {LABELS[key]} (median is 0; most months had none)",
                ))

    profits = {m.label: m.profit for m in months}
    revenues = {m.label: m.total_rev for m in months}
    loss_months = [label for label, p in profits.items() if p < 0]

    return YearAnalysis(
        fy_label=fy_label,
        months=months,
        line_stats=line_stats,
        quarters=quarters,
        outliers=outliers,
        loss_months=loss_months,
        best_profit_month=max(profits, key=profits.get),
        worst_profit_month=min(profits, key=profits.get),
        best_revenue_month=max(revenues, key=revenues.get),
        worst_revenue_month=min(revenues, key=revenues.get),
    )
