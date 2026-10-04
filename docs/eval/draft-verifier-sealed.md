# Draft verifier gate: verify_answer + LLM draft verifier

2026-10-05 · `draft_verifier_sealed.jsonl` · 30 bad and 30 good drafts × 3 runs · `gemini-3.5-flash-lite` (MINIMAL).

**FAIL** · bad drafts posted 0 (0) · good drafts blocked 1/90 (1.1%, ≤ 3%) · LLM check p50 960 ms, p95 1194 ms (≤ 700 ms) · timeouts or errors 0

- Bad drafts the LLM check alone lets through (all runs): 0/90
- Good drafts verify_answer blocks: 0/30

## Bad drafts posted (passed both layers)

- none

## Bad drafts the LLM check passes (verify_answer may still block them)

- none

## Good drafts blocked

- D104 run 0: rule 5: replies about after toner and before moisturiser instead of answering whether it goes before toner — "Apply it after toner and before moisturiser."
