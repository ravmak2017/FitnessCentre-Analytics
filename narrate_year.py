import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from llm_client import generate_brief
from output_paths import ANNUAL_DIR, ensure_all
from pnl_reader import read_pnl
from prompts import (
    SYSTEM_PROMPT_YEAR_ACCOUNTANT,
    SYSTEM_PROMPT_YEAR_OWNER,
    build_year_user_prompt,
)
from year_analyzer import analyze_year

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


AUDIENCES = {
    "owner": ("Owner", SYSTEM_PROMPT_YEAR_OWNER),
    "accountant": ("Accountant", SYSTEM_PROMPT_YEAR_ACCOUNTANT),
}


def main() -> int:
    load_dotenv(Path(__file__).parent / ".env", override=True)

    parser = argparse.ArgumentParser(description="Generate the annual P&L review for ABC Fitness Club.")
    parser.add_argument("--fy", help="Fiscal year as YYYY-YY (e.g. 2025-26). Defaults to FY of latest populated month.")
    parser.add_argument("--audience", choices=["owner", "accountant", "both"], default="both",
                        help="Which version(s) to generate. Default: both.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the prompts that would be sent and exit (no LLM call).")
    parser.add_argument("--no-open", action="store_true",
                        help="Do not open the brief(s) in the default app after generation.")
    args = parser.parse_args()

    print("Reading P&L tab from ABC Master sample.xlsx ...")
    months = read_pnl()
    print(f"  found {len(months)} populated months total: {months[0].label} to {months[-1].label}")

    result = analyze_year(months, fy_label=args.fy)
    print(f"Analyzing FY{result.fy_label} ({len(result.months)} months: "
          f"{result.months[0].label} to {result.months[-1].label})")
    print(f"  outliers: {len(result.outliers)}, loss months: {len(result.loss_months)}, "
          f"quarters: {len(result.quarters)}")

    user_prompt = build_year_user_prompt(result)

    if args.dry_run:
        print("\n--- USER PROMPT (shared across audiences) ---\n")
        print(user_prompt)
        return 0

    audience_keys = ["owner", "accountant"] if args.audience == "both" else [args.audience]
    ensure_all()
    output_paths: list[Path] = []
    total_input = total_output = 0

    for key in audience_keys:
        label, sys_prompt = AUDIENCES[key]
        print(f"\nCalling Claude Haiku 4.5 for the {label} version ...")
        try:
            brief, usage = generate_brief(sys_prompt, user_prompt)
        except anthropic.AuthenticationError:
            print("ERROR: Invalid or missing ANTHROPIC_API_KEY. Set it in .env or your environment.", file=sys.stderr)
            return 2
        except anthropic.RateLimitError as e:
            print(f"ERROR: Rate limited by the API: {e}", file=sys.stderr)
            return 3
        except anthropic.APIStatusError as e:
            print(f"ERROR: API returned status {e.status_code}: {e.message}", file=sys.stderr)
            return 4

        filename = f"annual_brief_FY{result.fy_label}_{key}.md"
        out_path = ANNUAL_DIR / filename
        footer = (
            f"\n\n---\n"
            f"*Source: `ABC Master sample.xlsx` P&L tab · FY: {result.fy_label} · Audience: {label} · "
            f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} by Claude Haiku 4.5 · "
            f"Tokens: input={usage['input_tokens']}, output={usage['output_tokens']}, "
            f"cache_read={usage['cache_read_input_tokens']}*\n"
        )
        out_path.write_text(brief.strip() + footer, encoding="utf-8")
        output_paths.append(out_path)
        total_input += usage["input_tokens"]
        total_output += usage["output_tokens"]
        print(f"  saved -> {out_path}")
        print(f"  tokens: input={usage['input_tokens']}, output={usage['output_tokens']}, "
              f"cache_read={usage['cache_read_input_tokens']}")

    print(f"\nDone. {len(output_paths)} file(s). "
          f"Total tokens: input={total_input}, output={total_output}.")

    if not args.no_open and hasattr(os, "startfile"):
        for p in output_paths:
            os.startfile(str(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
