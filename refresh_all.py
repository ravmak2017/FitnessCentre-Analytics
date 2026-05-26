"""End-to-end refresh: pipeline → AI briefs → anomaly scan → annual review.

Usage:
    python refresh_all.py                          # dummy source, all stages
    python refresh_all.py --source prod            # production source
    python refresh_all.py --skip-pipeline          # AI only (master Excel already fresh)
    python refresh_all.py --skip-ai                # pipeline only
    python refresh_all.py --month 2026-01          # narrate just one month
    python refresh_all.py --no-year                # skip annual review

Can be called as a script (CLI) or imported (`run_refresh(...)`).
Yields progress messages so a Streamlit progress bar can consume it.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterator

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).parent
PYTHON = sys.executable  # use the same interpreter Streamlit/CLI launched with


def _run(cmd: list[str], env: dict[str, str]) -> tuple[int, str]:
    """Run a subprocess, capture stdout+stderr together, return (rc, output)."""
    p = subprocess.run(
        cmd, cwd=HERE, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    return p.returncode, out.strip()


def run_refresh(
    source: str = "dummy",
    skip_pipeline: bool = False,
    skip_ai: bool = False,
    month: str | None = None,
    do_year: bool = True,
) -> Iterator[tuple[str, bool, str]]:
    """Yield (step_label, success, detail) per stage. Caller drives a progress bar."""
    from data_sources import SOURCES  # local import to keep CLI startup fast

    if source not in SOURCES:
        yield (f"Unknown source '{source}'", False, f"Valid: {list(SOURCES)}")
        return

    env = os.environ.copy()
    env["DATA_SOURCE"] = source
    env["PYTHONIOENCODING"] = "utf-8"
    src = SOURCES[source]

    # ── 1. Pipeline ─────────────────────────────────────────
    if not skip_pipeline:
        if not src.pipeline_script.exists():
            yield (
                f"1. Pipeline ({src.pipeline_label})",
                False,
                f"Script not found at {src.pipeline_script}. Edit data_sources.py to fix.",
            )
        else:
            yield (f"1. Pipeline · running {src.pipeline_label}", True, "starting …")
            rc, out = _run([PYTHON, str(src.pipeline_script)], env)
            yield (
                f"1. Pipeline · {src.pipeline_label}",
                rc == 0,
                _tail(out, 40),
            )
            if rc != 0:
                yield ("Aborting — pipeline failed", False, "fix pipeline first")
                return

    if skip_ai:
        return

    # ── 2. Discover months from the master Excel ───────────
    yield ("2. Reading P&L from master Excel", True, "discovering months …")
    try:
        # Import fresh under the env-var so it picks the right source
        from importlib import reload  # noqa: PLC0415

        import pnl_reader  # noqa: PLC0415
        reload(pnl_reader)
        months = pnl_reader.read_pnl()
        ym_list = [m.month.strftime("%Y-%m") for m in months]
    except Exception as e:
        yield ("2. Reading master Excel", False, f"{type(e).__name__}: {e}")
        return
    yield (
        f"2. P&L loaded · {len(ym_list)} months",
        True,
        f"{ym_list[0]} → {ym_list[-1]}" if ym_list else "no months",
    )

    targets = [month] if month else ym_list

    # ── 3. Monthly briefs ──────────────────────────────────
    for i, ym in enumerate(targets, start=1):
        rc, out = _run(
            [PYTHON, "narrate_month.py", "--month", ym, "--no-open"], env,
        )
        yield (
            f"3.{i:02d} narrate_month · {ym}",
            rc == 0,
            _tail(out, 6),
        )

    # ── 4. Anomaly scan (sentinel) ─────────────────────────
    rc, out = _run([PYTHON, "sentinel.py", "--all"], env)
    yield ("4. sentinel --all", rc == 0, _tail(out, 10))

    # ── 5. Annual review ───────────────────────────────────
    if do_year:
        rc, out = _run([PYTHON, "narrate_year.py", "--no-open"], env)
        yield ("5. narrate_year", rc == 0, _tail(out, 10))

    yield ("✅ Refresh complete", True, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def _tail(text: str, n_lines: int) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[-n_lines:])


def main() -> int:
    p = argparse.ArgumentParser(description="Refresh pipeline + AI outputs end-to-end.")
    p.add_argument("--source", choices=["dummy", "prod"], default="dummy")
    p.add_argument("--skip-pipeline", action="store_true",
                    help="AI only — assume master Excel is already current.")
    p.add_argument("--skip-ai", action="store_true",
                    help="Pipeline only — don't regenerate briefs/anomaly/annual.")
    p.add_argument("--month", help="Narrate only this month (YYYY-MM); skips others.")
    p.add_argument("--no-year", action="store_true",
                    help="Skip the annual review step.")
    args = p.parse_args()

    failed = 0
    for label, ok, detail in run_refresh(
        source=args.source,
        skip_pipeline=args.skip_pipeline,
        skip_ai=args.skip_ai,
        month=args.month,
        do_year=not args.no_year,
    ):
        flag = "✓" if ok else "✗"
        print(f"\n[{flag}] {label}")
        if detail:
            print(f"    {detail.replace(chr(10), chr(10) + '    ')}")
        if not ok:
            failed += 1

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
