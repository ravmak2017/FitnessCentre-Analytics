# Changelog

All notable changes to this project are documented in this file. The format
loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — Initial public release

### Added
- Six Streamlit pages: Home, Monthly Briefs, Annual Reviews, Anomaly Reports,
  Q&A Chat, Insights & Summary.
- End-to-end LLM pipeline with Claude Haiku 4.5 — monthly briefs, anomaly
  triage, owner + accountant annual reviews, RAG-grounded Q&A.
- Deterministic business-rules layer (`month_context.py`) that detects partial
  months and unposted month-end lines, then injects facts and hard rules into
  every prompt — preventing misleading MoM comparisons on incomplete data.
- Prompt caching (`cache_control: ephemeral`) for ~80% cost reduction on
  repeat Q&A turns.
- Structured-output JSON schemas for parseable LLM responses.
- ReportLab-based PDF export for every report and the full chat transcript.
- Indian-number formatting (`₹13.30L`, `₹13,29,810`) across all KPI tiles.
- Bilingual UI (English + Hindi) via a single `t()` translation helper.
- Mobile-responsive CSS (`@media (max-width: 768px)`).
- Sanitized 52-week sample dataset with 517 anonymized members across 8
  fictional branches.
- Pre-generated AI artifacts (12 briefs, 11 anomaly reports, 2 annual reviews)
  so the dashboard is fully explorable without an API key.

### Documentation
- [Architecture deep-dive](docs/ARCHITECTURE.md) — 6-layer design, file map,
  three non-obvious patterns explained.
- [Lakehouse Migration Guide](docs/Lakehouse_Migration_Guide.pdf) — 21-page
  learning reference for migrating to Azure Databricks + Unity Catalog + ADLS
  Gen2.
- [Project Components Reference](docs/Project_Components_Reference.pdf) —
  18-page component-by-component breakdown.
- [Streamlit Cloud deployment guide](docs/DEPLOY_STREAMLIT_CLOUD.md).
