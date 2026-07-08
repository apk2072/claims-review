# eval (package: claims_eval)

Eval dataset curation, weighted composite scoring, and GEPA-based prompt optimization — the closed-loop piece that turns human review verdicts into automated prompt improvements for the assistant agent.

- Weekly curation job pulls high-signal MLflow traces (human feedback, failed scorers, bookmarked traces)
- Weighted composite scorer: correctness 50%, safety 25%, relevance 12.5%, tool-call correctness 12.5%
- GEPA generates challenger prompts from curated failures; a promotion gate enforces safety/correctness floors plus a bootstrap CI check before publishing to the MLflow Prompt Registry

## Run locally

```bash
uv run --package claims-eval python -c "print('ok')"
uv run --package claims-eval pytest
```
