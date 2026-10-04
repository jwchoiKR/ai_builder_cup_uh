# Utterance agents · split3 · 2026-10-05

- **Agents:** ComplianceJudge + ContextJudge + FactChecker in parallel (production, D-099), on `gemini-3.5-flash-lite` (thinking MEDIUM).
- **Runs:** 100 eval cases × 3 runs = 300 case runs; every run scored. Timeouts are counted apart from wrong answers.
- **Script:** `backend/scripts/eval_agents.py`; production prompts in `prompts/`, the router prompt in `backend/scripts/experiments/prompts/`. Judge outputs get the production `post_validate`.

| Check | Correct / answered | Wrong | Timeout |
|---|---|---|---|
| judge · catches the violation (right rule) | 30/30 (100.0%) | 0 | 45 |
| judge · correction | 10/10 (100.0%) | 0 | 8 |
| judge · no alert on negated/quoted/approved wording | 10/10 (100.0%) | 0 | 20 |
| judge · leak: alert on a sentence with no compliance claim | 118/119 (99.2%) | 1 | 76 |
| judge · answer linking | 16/16 (100.0%) | 0 | 53 |
| judge · prompter points | 24/24 (100.0%) | 0 | 33 |
| judge · switch | 6/6 (100.0%) | 0 | 18 |
| facts (after quote check) · catches the wrong fact | 26/26 (100.0%) | 0 | 16 |
| facts (after quote check) · no note on a right fact | 25/25 (100.0%) | 0 | 17 |
| facts (raw) · catches the wrong fact | 26/26 (100.0%) | 0 | 16 |
| facts (raw) · no note on a right fact | 25/25 (100.0%) | 0 | 17 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 87/87 (100.0%) | 0 | 129 |
| facts (raw) · leak: note on a sentence that is not about facts | 87/87 (100.0%) | 0 | 129 |

- **Compliance verdict ready (red alert path):** p50 1252 · p95 2353 · max 2465 ms
- **Answer / prompter / switch verdict ready:** p50 2054 · p95 2459 · max 2481 ms
- **Fact verdict ready:** p50 2209 · p95 2896 · max 2987 ms
- **All done:** p50 2140 · p95 2933 · max 2947 ms
- **Timeouts:** {'compliance part': 141, 'context part': 214, 'fact checker': 162} of 300 each

## Wrong answers (case: what came back × runs)
- **judge · leak: alert on a sentence with no compliance claim:** H064: [{'span': 'forty-five percent hydration boost', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': False, 'is_quoted': False ×1
