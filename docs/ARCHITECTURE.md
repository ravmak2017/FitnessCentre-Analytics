# Architecture — ABC Analytics

A deeper look at how the pieces fit together. Read this if you're evaluating
the repo as a portfolio piece or thinking about adapting it.

---

## Layered design

The codebase is organized into 6 clean layers. Each lower layer is a strict
dependency of the layer above — nothing reaches sideways or backwards.

```
┌───────────────────────────────────────────────────────┐
│  6. UI Layer        Streamlit pages (5) + PDF export  │
├───────────────────────────────────────────────────────┤
│  5. LLM Layer       Claude Haiku 4.5 client wrappers  │
│                     (prompt cache, structured output) │
├───────────────────────────────────────────────────────┤
│  4. Prompt Layer    System prompts + user-prompt      │
│                     builders (one per task)           │
├───────────────────────────────────────────────────────┤
│  3. Logic Layer     analyzer, year_analyzer,          │
│                     anomaly_detector, month_context   │
├───────────────────────────────────────────────────────┤
│  2. Reader Layer    pnl_reader, membership_reader,    │
│                     qa_context                        │
├───────────────────────────────────────────────────────┤
│  1. Data Layer      Master Excel produced by pipeline │
│                     (P&L tab + Ultra/Premium tabs)    │
└───────────────────────────────────────────────────────┘
```

---

## File map

| File | Role |
|---|---|
| `Dashboard.py` | Streamlit entry point (home page) |
| `pages/1_Monthly_Briefs.py` | Per-month brief reader + PDF |
| `pages/2_Annual_Reviews.py` | FY review reader (Owner / Accountant / side-by-side) |
| `pages/3_Anomaly_Reports.py` | Severity-graded anomaly viewer |
| `pages/4_QA_Chat.py` | RAG-grounded chat over the P&L |
| `pages/5_Insights.py` | Interactive analytics (12 sections, all charts labelled) |
| `data_sources.py` | Single source of truth for paths (master Excel + AI output dirs) |
| `pnl_reader.py` | Reads the P&L tab, returns `MonthlyPnL` dataclasses |
| `membership_reader.py` | Reads Ultra/Premium tabs, builds client aggregates |
| `analyzer.py` | Month-over-month + rolling-average flagging logic |
| `year_analyzer.py` | FY totals, quarterly breakdown, outliers, loss months |
| `anomaly_detector.py` | 6 rule-based detectors (z-score, GM compression, …) |
| `month_context.py` | **The "consulting brain"** — partial-month detection, unposted-line awareness, pace-factor projection |
| `prompts.py` | All system prompts + user-prompt builders |
| `llm_client.py` | Wrapper around `anthropic.messages.create` with prompt caching |
| `qa_context.py` | RAG retriever — assembles full context (P&L + briefs) for Q&A |
| `narrate_month.py` | CLI: generate monthly brief |
| `narrate_year.py` | CLI: generate annual review (owner + accountant) |
| `sentinel.py` | CLI: run anomaly sentinel on one or all months |
| `ask_pnl.py` | CLI: REPL-style Q&A from the terminal |
| `refresh_all.py` | Orchestrator: pipeline → narrate_month → sentinel → narrate_year |
| `pdf_export.py` | ReportLab-based markdown→PDF and chat→PDF renderers |
| `theme.py` | Soft-light palette, KPI tile helper, Indian-number formatting, EN/HI translations |
| `output_paths.py` | PEP 562 `__getattr__` — re-resolves output dirs on every access |

---

## Three non-obvious design choices

### 1. Dynamic path resolution (PEP 562 `__getattr__`)

The dashboard lets the user switch between fiscal years via a sidebar
dropdown. If `BRIEFS_DIR` were resolved once at import time, Streamlit's
module cache would pin the dashboard to whichever source was active first.

Solution: `output_paths.py` exposes `BRIEFS_DIR` / `ANOMALIES_DIR` / `ANNUAL_DIR`
via module-level `__getattr__`, which calls `data_sources.ai_dirs()` fresh on
every page rerun. Existing `from output_paths import BRIEFS_DIR` keeps working
unchanged.

### 2. The business-rules layer (`month_context.py`)

A naïve LLM brief in a partial month produces misleading output ("revenue down
49%" when really the month is half over). The fix:

1. **Detection (deterministic):** `compute_context(target, history)` returns a
   `MonthContext` with `is_partial`, `days_elapsed`, `unposted_lines` (lines
   that are typically posted at month-end and currently show ₹0 while
   historical mean is non-zero).
2. **Prompt injection:** `render_context_block(ctx)` produces a "MONTH STATUS"
   block that ships at the top of every prompt.
3. **Hard rules in the system prompt:** banned-phrase list ("decline", "drop",
   "below prior", …) and a "Variant B" template that swaps the "What moved"
   section for a "Where things stand (to date)" with two sub-lists.
4. **Data masking:** in partial mode, `_line_row(partial=True)` strips
   `prior_month=` and `pct_change=` from the per-line data we feed the model
   — the model literally cannot cite a decline because we don't give it one.

The result: in May (a partial month), the brief reads like a consultant
("May 2026 is partial (24 of 31 days). Numbers below are to-date…"), not like
a script that printed a number.

### 3. Prompt caching ROI

Every system prompt is sent with `cache_control: {"type": "ephemeral"}`. The
first call seeds the cache (full system prompt billed); subsequent Q&A calls
on the same conversation hit the cache, paying ~10% of input cost.

For a 5-question Q&A session, this drops the cost from ~₹0.25 to ~₹0.05.

---

## Streamlit-specific patterns

- **Single multi-page app** (`Dashboard.py` + `pages/`) — clean URL paths
  (`/Monthly_Briefs`, `/Insights`).
- **`@st.cache_data`** on `read_pnl()` for instant rerenders.
- **`st.session_state["data_source"]`** for source-switching without restart.
- **`st.cache_data.clear()`** on dropdown change so the new master is read.
- **Soft-light palette** — high-contrast slate text on off-white, sky-blue
  accent. Decisions explained in `theme.py`.
- **Mobile-aware** — a `@media (max-width: 768px)` block shrinks hero text,
  KPI values, and chart label fonts so the dashboard reads well on a phone.

---

## What's NOT in the public repo

The production deployment for a real fitness centre additionally includes:

- The Excel pipeline (`pipeline.py`) — proprietary to that fitness centre's setup
  (sheet schemas, recon rules, ingestion folder layout).
- The Cloudflare Tunnel config + named tunnel.
- A nightly cron that runs `refresh_all.py --skip-pipeline` to refresh AI
  outputs against the latest Excel master.
- Some pitch decks (`*.pptx`) used to sell the platform to other fitness centre owners.

If you'd like to evaluate the production version (e.g. for licensing),
please reach out.
