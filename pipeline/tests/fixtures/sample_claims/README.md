# Sample claim fixtures

Synthetic (never-real-PHI) claim documents used to exercise the pipeline. Regenerate with:

```bash
uv run python pipeline/tests/fixtures/sample_claims/generate_fixtures.py
```

| Fixture | Exercises |
|---|---|
| `clean_high_confidence.png` | Sharp text, all fields present — should flow through bronze/silver/gold and land above the 0.92 auto-verdict threshold |
| `blurry_low_confidence.png` | Same content, gaussian-blurred to simulate a low-quality scan — should drag down `ai_parse_document`'s parse-confidence component and route to human review |
| `missing_fields.png` | Several required fields left blank — should drag down the completeness component of the composite confidence score |
| `wrong_document_type.png` | A grocery receipt, not a claim form at all — exercises `ai_classify` correctly flagging the wrong document type |

All identifiers are obviously fake (e.g. `Jane Test Doe`, `TEST-000000`) — this project never processes real PHI.
