import anthropic

MODEL = "claude-haiku-4-5"
MAX_TOKENS_BRIEF = 3000
MAX_TOKENS_QA = 2000

SEED_QUESTIONS_EN = [
    "Give me a summary of FY2025-26",
    "Which months had losses or data integrity concerns?",
    "What was our best month and why?",
    "How did revenue trend across quarters?",
    "Compare Q1 (Apr-Jun) vs Q4 (Jan-Mar)",
]

QA_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "next_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "next_questions"],
    "additionalProperties": False,
}


def _system_block(text: str) -> list[dict]:
    return [{
        "type": "text",
        "text": text,
        "cache_control": {"type": "ephemeral"},
    }]


def _usage_dict(usage: anthropic.types.Usage) -> dict:
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_create,
        "total_input_tokens": usage.input_tokens + cache_read + cache_create,
    }


def generate_brief(system_prompt: str, user_prompt: str) -> tuple[str, dict]:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_BRIEF,
        system=_system_block(system_prompt),
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    return text, _usage_dict(response.usage)


def ask_qa(
    system_prompt: str,
    messages: list[dict],
    *,
    client: anthropic.Anthropic | None = None,
) -> tuple[dict, dict]:
    """Call Claude with structured Q&A JSON (answer + next_questions)."""
    if client is None:
        client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_QA,
        system=_system_block(system_prompt),
        messages=messages,
        output_config={"format": {"type": "json_schema", "schema": QA_OUTPUT_SCHEMA}},
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    return json.loads(text), _usage_dict(response.usage)
