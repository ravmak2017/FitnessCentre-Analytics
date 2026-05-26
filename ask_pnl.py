import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from prompts import SYSTEM_PROMPT_QA
from qa_context import build_full_context

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SESSIONS_DIR = Path(__file__).parent / "qa_sessions"
MODEL = "claude-haiku-4-5"
MAX_TOKENS = 2000

SEED_QUESTIONS = [
    "Give me a summary of FY2025-26",
    "Which months had losses or data integrity concerns?",
    "What was our best month and why?",
    "How did revenue trend across quarters?",
    "Compare Q1 (Apr-Jun) vs Q4 (Jan-Mar)",
]

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "next_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "next_questions"],
    "additionalProperties": False,
}


def _divider(char: str = "=", width: int = 64) -> str:
    return char * width


def render_menu(questions: list[str], allow_back: bool) -> None:
    print()
    print(_divider("="))
    print("What would you like to explore?")
    print(_divider("="))
    for i, q in enumerate(questions[:5], 1):
        print(f"  {i}. {q}")
    print("  c. Ask a custom question")
    if allow_back:
        print("  b. Back to the initial menu")
    print("  /save  Save this session now")
    print("  x. Exit")


def prompt_user(questions: list[str]) -> tuple[str, str | None]:
    while True:
        try:
            choice = input("\nPick: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "exit", None
        if not choice:
            continue
        if choice in ("x", "exit", "quit"):
            return "exit", None
        if choice in ("b", "back"):
            return "back", None
        if choice in ("c", "custom"):
            try:
                q = input("Your question: ").strip()
            except (EOFError, KeyboardInterrupt):
                return "exit", None
            if q:
                return "ask", q
            continue
        if choice in ("/save", "save"):
            return "save", None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < min(len(questions), 5):
                return "ask", questions[idx]
        print("  Invalid choice. Pick a number (1-5), 'c' (custom), 'b' (back), '/save', or 'x' (exit).")


def save_session(transcript: list[str], total_in: int, total_out: int) -> Path | None:
    if len(transcript) <= 1:
        return None
    SESSIONS_DIR.mkdir(exist_ok=True)
    name = f"qa_{datetime.now().strftime('%Y-%m-%d_%H%M')}.md"
    out = SESSIONS_DIR / name
    transcript.append(
        f"\n---\n*Session totals: input_tokens={total_in}, output_tokens={total_out}*"
    )
    out.write_text("\n".join(transcript), encoding="utf-8")
    return out


def call_llm(client, system_prompt: str, messages: list[dict]) -> tuple[dict, anthropic.types.Usage]:
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=messages,
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    return data, response.usage


def main() -> int:
    load_dotenv(Path(__file__).parent / ".env", override=True)
    parser = argparse.ArgumentParser(description="Guided P&L Q&A for ABC Fitness Club.")
    parser.parse_args()

    print("Loading P&L context...")
    context, meta = build_full_context()
    print(f"  {meta['months']} months ({meta['first_month']} to {meta['last_month']})")
    print(f"  {meta['briefs_count']} brief(s)/report(s) loaded: {', '.join(meta['briefs_filenames']) or '(none)'}")
    print(f"  context: {meta['context_chars']:,} chars (~{meta['context_chars']//4:,} tokens)")

    system_with_context = SYSTEM_PROMPT_QA + "\n\n" + context
    client = anthropic.Anthropic()

    messages: list[dict] = []
    transcript: list[str] = [
        f"# Q&A Session — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"\n*Context: {meta['months']} months ({meta['first_month']} -> {meta['last_month']}), "
        f"{meta['briefs_count']} brief(s)/report(s) loaded.*\n",
    ]
    next_menu = list(SEED_QUESTIONS)
    in_initial = True
    total_in = total_out = 0
    saved_paths: list[Path] = []

    print("\nReady. Press a number to pick a question, 'c' for custom, 'x' to exit.")

    while True:
        render_menu(next_menu, allow_back=not in_initial)
        action, payload = prompt_user(next_menu)

        if action == "exit":
            break
        if action == "save":
            p = save_session(list(transcript), total_in, total_out)
            if p:
                print(f"  -> session saved: {p}")
                saved_paths.append(p)
            else:
                print("  (nothing to save yet)")
            continue
        if action == "back":
            messages = []
            transcript.append("\n---\n*(returned to initial menu)*\n---")
            next_menu = list(SEED_QUESTIONS)
            in_initial = True
            continue

        question = payload
        print()
        print(_divider("-"))
        print(f"> {question}")
        print(_divider("-"))
        messages.append({"role": "user", "content": question})

        try:
            data, usage = call_llm(client, system_with_context, messages)
        except anthropic.AuthenticationError:
            print("ERROR: Invalid or missing ANTHROPIC_API_KEY.", file=sys.stderr)
            return 2
        except anthropic.RateLimitError as e:
            print(f"ERROR: Rate limited: {e}", file=sys.stderr)
            return 3
        except anthropic.APIStatusError as e:
            print(f"ERROR: API status {e.status_code}: {e.message}", file=sys.stderr)
            return 4
        except json.JSONDecodeError as e:
            print(f"ERROR: Failed to parse LLM JSON response: {e}", file=sys.stderr)
            messages.pop()
            continue

        answer = data.get("answer", "(no answer returned)")
        next_qs = data.get("next_questions") or []
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
        total_in += usage.input_tokens + cache_read + cache_create
        total_out += usage.output_tokens

        print(f"\n{answer}\n")
        print(f"  [tokens: uncached_in={usage.input_tokens}, cache_write={cache_create}, "
              f"cache_read={cache_read}, out={usage.output_tokens}]")

        messages.append({"role": "assistant", "content": answer})
        transcript.append(f"\n## Q: {question}\n\n{answer}")

        next_menu = next_qs[:5] if next_qs else list(SEED_QUESTIONS)
        in_initial = False

    final_path = save_session(transcript, total_in, total_out)
    if final_path and final_path not in saved_paths:
        print(f"\nSession saved -> {final_path}")
    print(f"Total tokens this session: input={total_in}, output={total_out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
