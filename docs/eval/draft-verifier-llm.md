# Draft verifier gate: verify_answer + LLM draft verifier

2026-10-05 · `draft_verifier_cases.jsonl` · 30 bad and 30 good drafts × 3 runs · `gemini-3.5-flash-lite` (MINIMAL).

**FAIL** · bad drafts posted 0 (0) · good drafts blocked 0/90 (0.0%, ≤ 3%) · LLM check p50 1001 ms, p95 1243 ms (≤ 700 ms) · timeouts or errors 1

- Bad drafts the LLM check alone lets through (all runs): 3/90
- Good drafts verify_answer blocks: 0/30

## Bad drafts posted (passed both layers)

- none

## Bad drafts the LLM check passes (verify_answer may still block them)

- D007 run 0 (code block): Drops the in-house qualifier from a numerical test result.
- D007 run 1 (code block): Drops the in-house qualifier from a numerical test result.
- D007 run 2 (code block): Drops the in-house qualifier from a numerical test result.

## Good drafts blocked

- none
