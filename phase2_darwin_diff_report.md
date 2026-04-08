# Phase 2: Darwin Engine Real Diffs — Implementation Report

## Files Changed

### 1. `dharma_swarm/evolution.py`

**New method: `_generate_real_diff`** (lines 2684–2789)
- Added as a method on the `DarwinEngine` class
- Located between `_parse_llm_proposal` (line 2668) and `generate_proposal` (line 2791)
- Takes `provider`, `component`, `description`, `improvement_direction`, `model` as arguments
- Reads the target file for context (first 200 lines)
- Calls the LLM provider with a focused diff-generation prompt
- Returns empty string on: empty inputs, SKIP response, invalid format, or exceptions
- Tracks token usage via `self._session_tokens_used`

**Wired into `generate_proposal`** (lines 2939–2948)
- After the proposal is created (line 2937), if `proposal.diff` is empty, calls `_generate_real_diff`
- Uses the `provider` and `model` already available in `generate_proposal`'s scope
- Passes the `think` notes as `improvement_direction` for additional context
- Updated trace metadata to include `diff_source` field (first_pass / second_pass / none)
- Updated log message to include diff line count

### 2. `tests/test_darwin_diff.py` (NEW — 284 lines)

**TestGenerateRealDiff class (8 tests):**
1. `test_valid_diff_returned` — mock provider returns valid diff → returns diff string
2. `test_skip_response_returns_empty` — provider returns "SKIP" → returns ""
3. `test_invalid_format_returns_empty` — response not starting with "---" → returns ""
4. `test_provider_exception_returns_empty` — provider raises RuntimeError → returns "" (no crash)
5. `test_empty_component_skips_llm_call` — empty component → returns "", no LLM call made
6. `test_empty_description_skips_llm_call` — empty description → returns "", no LLM call made
7. `test_token_tracking` — verifies session token counter is incremented
8. `test_improvement_direction_passed_to_prompt` — checks prompt includes direction text

**TestGenerateProposalWiresDiff class (2 tests):**
9. `test_second_llm_call_when_first_has_no_diff` — first LLM returns no diff, second call generates one → 2 LLM calls, diff populated
10. `test_no_second_call_when_first_has_diff` — first LLM includes diff → only 1 LLM call

## Test Results

```
tests/test_darwin_diff.py:   10 passed
tests/test_evolution.py:     92 passed (zero regressions)
```

## Key Design Decisions

1. **Provider passed explicitly**: `_generate_real_diff` receives the provider as a parameter (same one available in `generate_proposal`), rather than using `complete_via_preferred_runtime_providers`, keeping the method testable and consistent with the existing DarwinEngine pattern.

2. **Second call is conditional**: Only fires when `proposal.diff` is empty after the first LLM call. If the first call already produced a diff (via the ```diff block in the response), no second call is made.

3. **Graceful degradation**: All failures (provider exceptions, invalid format, SKIP responses) result in an empty diff — the proposal proceeds without a diff but doesn't crash.

4. **Token tracking**: The second LLM call's token usage is added to `_session_tokens_used` so the daily token budget is respected.

5. **Context window**: Reads first 200 lines (capped at 3000 chars) of the target file, giving the LLM enough context for a targeted diff without exceeding prompt limits.
