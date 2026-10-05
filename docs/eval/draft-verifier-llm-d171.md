# Draft verifier gate: verify_answer + LLM draft verifier

2026-10-05 · `draft_verifier_cases.jsonl` · 34 bad and 32 good drafts × 3 runs · `gemini-3.5-flash-lite` (MINIMAL).

**FAIL** · bad drafts posted 0 (0) · good drafts blocked 0/96 (0.0%, ≤ 3%) · LLM check p50 1003 ms, p95 1270 ms (≤ 700 ms) · timeouts or errors 0

- Bad drafts the LLM check alone lets through (all runs): 3/102
- Good drafts verify_answer blocks: 0/32

## Bad drafts posted (passed both layers)

- none

## Bad drafts the LLM check passes (verify_answer may still block them)

- D007 run 0 (code block): Drops the in-house qualifier from a numerical test result.
- D007 run 1 (code block): Drops the in-house qualifier from a numerical test result.
- D007 run 2 (code block): Drops the in-house qualifier from a numerical test result.

## Good drafts blocked

- none
