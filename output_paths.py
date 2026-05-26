"""Shared paths + filename helpers for the AI output structure.

The active subfolder is decided by `data_sources.active_source()`. Since the
unified workspace lets the user switch between Current Year and Prior Year via
the sidebar, these paths MUST be re-resolved on every access — otherwise a
cached value from the first import pins the dashboard to whichever source was
active first.

`ANOMALIES_DIR`, `BRIEFS_DIR`, `ANNUAL_DIR` are exposed via module-level
`__getattr__` (PEP 562). Python's `from output_paths import BRIEFS_DIR` calls
`__getattr__('BRIEFS_DIR')` because there is no regular module attribute by
that name — and because Streamlit re-executes the page script on every rerun,
the value is fresh each time the dropdown changes.
"""
from pathlib import Path

from data_sources import ai_dirs


def _resolve_dirs() -> tuple[Path, Path, Path]:
    return ai_dirs()


def __getattr__(name: str) -> Path:
    """Dynamic resolution of BRIEFS_DIR / ANOMALIES_DIR / ANNUAL_DIR."""
    if name == "ANOMALIES_DIR":
        return _resolve_dirs()[0]
    if name == "BRIEFS_DIR":
        return _resolve_dirs()[1]
    if name == "ANNUAL_DIR":
        return _resolve_dirs()[2]
    raise AttributeError(f"module 'output_paths' has no attribute {name!r}")


def fy_position(year_month: str) -> int:
    """Return 1-12 for April-March of an FY. E.g. '2025-04' -> 1, '2026-03' -> 12."""
    y, m = map(int, year_month.split("-"))
    return m - 3 if m >= 4 else m + 9


def prefixed(year_month: str, base_name: str) -> str:
    """Return '01. monthly_brief_2025-04.md' style filename."""
    return f"{fy_position(year_month):02d}. {base_name}"


def ensure_all() -> None:
    for d in _resolve_dirs():
        d.mkdir(parents=True, exist_ok=True)
