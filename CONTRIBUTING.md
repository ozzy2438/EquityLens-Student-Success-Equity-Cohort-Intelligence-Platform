# Contribution workflow

Use a short-lived branch such as `feature/day1-ingestion-foundation`. Keep raw
runtime artifacts out of Git. Changes to source URLs, validation logic, or
manifest schemas require tests and an explanation in the pull request.

Before requesting review, run:

```bash
ruff check .
ruff format --check .
pytest
```

The pull request should state the source publication page, whether publisher
bytes or metadata changed, the targeted smoke-test result, and any unresolved
source risk. Merge only after the GitHub Actions quality gate succeeds. At least
one reviewer should validate registry changes against the publisher page.
