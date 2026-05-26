"""Portfolio repo — points at a sanitized 52-week sample dataset.

All names + locations have been anonymized. Financial figures were already
synthetic (this dataset is a 52-week prototype, not real production data).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent
MASTER_PATH = HERE / "sample_data" / "ABC Master sample.xlsx"
AI_OUTPUT_ROOT = HERE / "AI- Output"


@dataclass(frozen=True)
class DataSource:
    key: str
    label: str
    master_path: Path
    pipeline_script: Path
    pipeline_label: str
    output_subdir: str


SAMPLE = DataSource(
    key="sample",
    label="Sample · 52-week prototype",
    master_path=MASTER_PATH,
    pipeline_script=HERE / "pipeline.py",  # placeholder, not shipped
    pipeline_label="(sample data — pipeline omitted in public repo)",
    output_subdir="",
)

SOURCES: dict[str, DataSource] = {SAMPLE.key: SAMPLE}


def active_source() -> DataSource:
    return SAMPLE


def master_path() -> Path:
    return MASTER_PATH


def ai_dirs() -> tuple[Path, Path, Path]:
    return (
        AI_OUTPUT_ROOT / "1. Anomaly",
        AI_OUTPUT_ROOT / "2. Brief",
        AI_OUTPUT_ROOT / "3. Annual brief",
    )


def require_master_or_stop() -> bool:
    import streamlit as st  # noqa: PLC0415

    if MASTER_PATH.exists():
        return True
    st.error("Sample data file missing.")
    st.markdown(
        f"Expected: `{MASTER_PATH.name}` inside the `sample_data/` folder. "
        "Re-clone the repo or restore the file."
    )
    st.stop()
    return False
