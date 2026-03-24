# dharma_verify

AI Code Verification Platform. Scores AI-generated code against 6 quality dimensions, tracks comprehension debt, and produces structured PR reviews.

## Quick Start

```python
from dharma_swarm.verify import score_diff, review_pr, format_review_comment

# Score a code diff
score = score_diff("def login(pw): return eval(pw)")
print(f"Score: {score.overall:.0%}")
print(f"Safety: {score.dimensions['safety']:.0%}")

# Full PR review
review = review_pr(
    "def hello(): return 'world'",
    pr_title="Add greeting",
)
print(f"Verdict: {review.verdict}")  # APPROVE / COMMENT / REQUEST_CHANGES

# Format as GitHub comment
comment = format_review_comment(review)
```

## API

```bash
# Health check
curl http://localhost:8000/api/verify/health

# Score a diff
curl -X POST http://localhost:8000/api/verify/score \
  -H "Content-Type: application/json" \
  -d '{"diff": "def hello(): pass"}'

# Full review
curl -X POST http://localhost:8000/api/verify/review \
  -H "Content-Type: application/json" \
  -d '{"diff": "...", "title": "PR Title", "body": "PR Description"}'
```

## Scoring Dimensions

| Dimension | What It Measures |
|-----------|-----------------|
| correctness | Tests present, assertions meaningful |
| clarity | Line length, naming, no magic numbers |
| safety | No eval/exec, no hardcoded secrets, no shell injection |
| completeness | Docstrings, error handling, type hints |
| efficiency | No obvious O(n^2), clean imports |
| governance | Protected files not touched, telos alignment |

## Architecture

```
PR Diff → scorer.py → 6 dimensions → reviewer.py → verdict → reporter.py → GitHub comment
                                          ↓
                              flywheel_bridge.py → trajectory_collector → training data
                                          ↓
                              comprehension.py → debt tracking over time
```

## GitHub App Webhook

Set environment variables:
```bash
export DHARMA_VERIFY_WEBHOOK_SECRET="your-webhook-secret"
```

The webhook endpoint at `/api/verify/webhook` handles `pull_request` events (opened, synchronized, reopened).
