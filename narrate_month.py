import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from analyzer import analyze
from data_sources import active_source
from llm_client import generate_brief
from month_context import compute_context, render_context_block
from output_paths import BRIEFS_DIR, ensure_all, prefixed
from pnl_reader import read_pnl
from prompts import SYSTEM_PROMPT, build_user_prompt


def main() -> int:
    load_dotenv(Path(__file__).parent / ".env", override=True)

    parser = argparse.ArgumentParser(description="Generate the monthly P&L brief for ABC Fitness Club.")
    parser.add_argument("--month", help="Target month as YYYY-MM (e.g. 2026-03). Defaults to latest populated month.")
    parser.add_argument("--dry-run", action="store_true", help="Print the prompt that would be sent and exit (no LLM call).")
    parser.add_argument("--no-open", action="store_true", help="Do not open the brief in the default app after generation.")
    args = parser.parse_args()

    src = active_source()
    print(f"Reading P&L from {src.master_path.name} ...")
    months = read_pnl()
    print(f"  found {len(months)} populated months: {months[0].label} to {months[-1].label}")

    result = analyze(months, target_month=args.month)
    print(f"Analyzing {result.target.label} vs {result.prior.label if result.prior else 'n/a'} "
          f"(rolling avg from {len(result.rolling_months)} prior months)")
    print(f"  {len(result.flagged)} flagged movement(s), {len(result.steady)} steady line(s)")

    # Compute calendar context (partial month detection, unposted month-end lines)
    ctx = compute_context(result.target, months)
    if ctx.is_partial:
        print(f"  ⚠ PARTIAL MONTH: {ctx.days_elapsed}/{ctx.days_in_month} days elapsed "
              f"({ctx.completeness_pct*100:.0f}%)")
        if ctx.unposted_lines:
            print(f"  ⚠ Unposted month-end lines: {', '.join(ctx.unposted_lines)}")
    context_block = render_context_block(ctx)

    user_prompt = build_user_prompt(result, context_block=context_block,
                                      is_partial=ctx.is_partial)

    if args.dry_run:
        print("\n--- SYSTEM PROMPT ---\n")
        print(SYSTEM_PROMPT)
        print("\n--- USER PROMPT ---\n")
        print(user_prompt)
        return 0

    print(f"Calling Claude Haiku 4.5 ...")
    try:
        brief, usage = generate_brief(SYSTEM_PROMPT, user_prompt)
    except anthropic.AuthenticationError:
        print("ERROR: Invalid or missing ANTHROPIC_API_KEY. Set it in .env or your environment.", file=sys.stderr)
        return 2
    except anthropic.RateLimitError as e:
        print(f"ERROR: Rate limited by the API: {e}", file=sys.stderr)
        return 3
    except anthropic.APIStatusError as e:
        print(f"ERROR: API returned status {e.status_code}: {e.message}", file=sys.stderr)
        return 4

    ensure_all()
    ym = result.target.month.strftime("%Y-%m")
    filename = prefixed(ym, f"monthly_brief_{ym}.md")
    out_path = BRIEFS_DIR / filename

    partial_note = (
        f" · ⚠ PARTIAL MONTH ({ctx.days_elapsed}/{ctx.days_in_month} days)"
        if ctx.is_partial else ""
    )
    footer = (
        f"\n\n---\n"
        f"*Source: `{src.master_path.name}` P&L tab · Target: {result.target.label}{partial_note} · "
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} by Claude Haiku 4.5 · "
        f"Tokens: input={usage['input_tokens']}, output={usage['output_tokens']}, "
        f"cache_read={usage['cache_read_input_tokens']}*\n"
    )

    out_path.write_text(brief.strip() + footer, encoding="utf-8")
    print(f"\nBrief saved -> {out_path}")
    print(f"  tokens: input={usage['input_tokens']}, output={usage['output_tokens']}, "
          f"cache_creation={usage['cache_creation_input_tokens']}, cache_read={usage['cache_read_input_tokens']}")

    if not args.no_open and hasattr(os, "startfile"):
        os.startfile(str(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
