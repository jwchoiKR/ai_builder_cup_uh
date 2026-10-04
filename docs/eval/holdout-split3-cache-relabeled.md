# Utterance agents · split3 · 2026-10-05

- **Agents:** ComplianceJudge + ContextJudge + FactChecker in parallel (production, D-099), on `gemini-3.5-flash-lite` (thinking MINIMAL).
- **Runs:** 100 eval cases × 3 runs = 300 case runs; every run scored. Timeouts are counted apart from wrong answers.
- **Script:** `backend/scripts/eval_agents.py`; production prompts in `prompts/`, the router prompt in `backend/scripts/experiments/prompts/`. Judge outputs get the production `post_validate`.

| Check | Correct / answered | Wrong | Timeout |
|---|---|---|---|
| judge · catches the violation (right rule) | 75/75 (100.0%) | 0 | 0 |
| judge · correction | 18/18 (100.0%) | 0 | 0 |
| judge · no alert on negated/quoted/approved wording | 29/30 (96.7%) | 1 | 0 |
| judge · leak: alert on a sentence with no compliance claim | 192/195 (98.5%) | 3 | 0 |
| judge · answer linking | 69/69 (100.0%) | 0 | 0 |
| judge · prompter points | 57/57 (100.0%) | 0 | 0 |
| judge · switch | 24/24 (100.0%) | 0 | 0 |
| facts (after quote check) · catches the wrong fact | 39/42 (92.9%) | 3 | 0 |
| facts (after quote check) · no note on a right fact | 42/42 (100.0%) | 0 | 0 |
| facts (raw) · catches the wrong fact | 42/42 (100.0%) | 0 | 0 |
| facts (raw) · no note on a right fact | 42/42 (100.0%) | 0 | 0 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 216/216 (100.0%) | 0 | 0 |
| facts (raw) · leak: note on a sentence that is not about facts | 176/216 (81.5%) | 40 | 0 |

- **Compliance verdict ready (red alert path):** p50 1030 · p95 1242 · max 1683 ms
- **Answer / prompter / switch verdict ready:** p50 1210 · p95 1400 · max 1674 ms
- **Fact verdict ready:** p50 1179 · p95 1643 · max 2049 ms
- **All done:** p50 1266 · p95 1643 · max 2049 ms
- **Timeouts:** none of 300 each

## Wrong answers (case: what came back × runs)
- **judge · no alert on negated/quoted/approved wording:** H032: [{'span': 'forty-eight hour patch test', 'rule_id': 'BRAND-SUPERLATIVE', 'severity': 'MEDIUM', 'is_negated': False, 'is_quoted': False, 'say_ins ×1
- **judge · leak: alert on a sentence with no compliance claim:** H064: [{'span': 'forty-five percent hydration boost', 'rule_id': 'BRAND-SUPERLATIVE', 'severity': 'MEDIUM', 'is_negated': False, 'is_quoted': False, ' ×2; H076: [{'span': 'always do a patch test first', 'rule_id': 'BRAND-ABSOLUTE-SAFETY', 'severity': 'MEDIUM', 'is_negated': False, 'is_quoted': False, 'sa ×1
- **facts (after quote check) · catches the wrong fact:** H046: [] ×3
- **facts (raw) · leak: note on a sentence that is not about facts:** H001: [{'span': 'this cream completely cures the inflammation', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value': 'completely cur ×2; H004: [{'span': 'the moisture retention is permanent', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'permanent', 'verdict ×1; H005: [{'span': 'physically reactivates your dormant skin cells to regenerate fresh tissue', 'field': 'other', 'product_id': 'ampoule_deep_hydration', ×1; H006: [{'span': 'will fill them up and erase them completely', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'Treats acne, ×1; H007: [{'span': 'totally safe for expecting mothers', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value': 'totally safe', 'verdict' ×1; H009: [{'span': 'bleaches out stubborn melanin', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'bleaches out melanin', 've ×1
