import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from anomaly_detector import build_report
from data_sources import active_source
from llm_client import generate_brief
from month_context import compute_context, render_context_block
from output_paths import ANOMALIES_DIR, ensure_all, prefixed
from pnl_reader import read_pnl
from prompts import SYSTEM_PROMPT_ANOMALY, build_anomaly_user_prompt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def _resolve_target(months, target_month: str | None):
    if target_month:
        match = [m for m in months if m.month.strftime("%Y-%m") == target_month]
        if not match:
            raise ValueError(f"Month {target_month} not found in data")
        return match[0]
    return months[-1]


def _run_one(target, history, *, dry_run: bool) -> tuple[Path | None, dict]:
    report = build_report(target, history)
    print(f"  detected {len(report.anomalies)} anomaly/anomalies "
          f"(critical={len(report.by_severity['critical'])}, "
          f"high={len(report.by_severity['high'])}, "
          f"medium={len(report.by_severity['medium'])}, "
          f"low={len(report.by_severity['low'])})")
    print(f"  verdict: {report.overall_verdict}")

    ctx = compute_context(target, history)
    if ctx.is_partial:
        print(f"  ⚠ PARTIAL MONTH: {ctx.days_elapsed}/{ctx.days_in_month} days "
              f"({ctx.completeness_pct*100:.0f}%) — anomalies will be judged accordingly")

    user_prompt = render_context_block(ctx) + "\n" + build_anomaly_user_prompt(report)

    if dry_run:
        print("\n--- USER PROMPT ---\n")
        print(user_prompt)
        return None, {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0}

    print(f"  calling Claude Haiku 4.5 ...")
    brief, usage = generate_brief(SYSTEM_PROMPT_ANOMALY, user_prompt)
    ensure_all()
    ym = target.month.strftime("%Y-%m")
    filename = prefixed(ym, f"anomaly_report_{ym}.md")
    out_path = ANOMALIES_DIR / filename
    partial_note = (
        f" · ⚠ PARTIAL MONTH ({ctx.days_elapsed}/{ctx.days_in_month} days)"
        if ctx.is_partial else ""
    )
    src = active_source()
    footer = (
        f"\n\n---\n"
        f"*Source: `{src.master_path.name}` P&L tab · Target: {target.label}{partial_note} · "
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} by Claude Haiku 4.5 · "
        f"Tokens: input={usage['input_tokens']}, output={usage['output_tokens']}, "
        f"cache_read={usage['cache_read_input_tokens']}*\n"
    )
    out_path.write_text(brief.strip() + footer, encoding="utf-8")
    print(f"  saved -> {out_path}")
    return out_path, usage


def main() -> int:
    load_dotenv(Path(__file__).parent / ".env", override=True)

    parser = argparse.ArgumentParser(description="Anomaly Sentinel: triage suspicious months in the ABC P&L.")
    parser.add_argument("--month", help="Target month as YYYY-MM. Defaults to latest populated month.")
    parser.add_argument("--all", action="store_true",
                        help="Sweep every month in the dataset (each compared against everything before it).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the prompt that would be sent and exit (no LLM call).")
    parser.add_argument("--no-open", action="store_true",
                        help="Do not open the report(s) in the default app after generation.")
    args = parser.parse_args()

    src = active_source()
    print(f"Reading P&L from {src.master_path.name} ...")
    months = read_pnl()
    print(f"  found {len(months)} populated months: {months[0].label} to {months[-1].label}")

    if args.all and args.month:
        print("ERROR: --all and --month cannot be combined.", file=sys.stderr)
        return 1

    targets: list = []
    if args.all:
        targets = [m for m in months[1:]]
        print(f"\nSweeping {len(targets)} months ({months[1].label} to {months[-1].label}).")
    else:
        targets = [_resolve_target(months, args.month)]
        print(f"\nTargeting: {targets[0].label}")

    output_paths: list[Path] = []
    total_input = total_output = 0

    try:
        for target in targets:
            target_idx = months.index(target)
            history = months[:target_idx]
            if not history:
                print(f"\n[{target.label}] skipping — no prior months for context.")
                continue
            print(f"\n[{target.label}] history: {len(history)} prior months")
            out_path, usage = _run_one(target, history, dry_run=args.dry_run)
            if out_path:
                output_paths.append(out_path)
            total_input += usage["input_tokens"]
            total_output += usage["output_tokens"]
    except anthropic.AuthenticationError:
        print("ERROR: Invalid or missing ANTHROPIC_API_KEY. Set it in .env or your environment.", file=sys.stderr)
        return 2
    except anthropic.RateLimitError as e:
        print(f"ERROR: Rate limited by the API: {e}", file=sys.stderr)
        return 3
    except anthropic.APIStatusError as e:
        print(f"ERROR: API returned status {e.status_code}: {e.message}", file=sys.stderr)
        return 4

    if not args.dry_run:
        print(f"\nDone. {len(output_paths)} file(s). "
              f"Total tokens: input={total_input}, output={total_output}.")

    if not args.no_open and not args.dry_run and hasattr(os, "startfile"):
        for p in output_paths:
            os.startfile(str(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
