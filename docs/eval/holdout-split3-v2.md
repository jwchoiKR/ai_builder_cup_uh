# Utterance agents · split3 · 2026-10-05

- **Agents:** ComplianceJudge + ContextJudge + FactChecker in parallel (production, D-099), on `gemini-3.5-flash-lite` (thinking MINIMAL).
- **Runs:** 100 eval cases × 3 runs = 300 case runs; every run scored. Timeouts are counted apart from wrong answers.
- **Script:** `backend/scripts/eval_agents.py`; production prompts in `prompts/`, the router prompt in `backend/scripts/experiments/prompts/`. Judge outputs get the production `post_validate`.

| Check | Correct / answered | Wrong | Timeout |
|---|---|---|---|
| judge · catches the violation (right rule) | 75/75 (100.0%) | 0 | 0 |
| judge · correction | 18/18 (100.0%) | 0 | 0 |
| judge · no alert on negated/quoted/approved wording | 30/30 (100.0%) | 0 | 0 |
| judge · leak: alert on a sentence with no compliance claim | 189/195 (96.9%) | 6 | 0 |
| judge · answer linking | 69/69 (100.0%) | 0 | 0 |
| judge · prompter points | 57/57 (100.0%) | 0 | 0 |
| judge · switch | 24/24 (100.0%) | 0 | 0 |
| facts (after quote check) · catches the wrong fact | 42/42 (100.0%) | 0 | 0 |
| facts (after quote check) · no note on a right fact | 42/42 (100.0%) | 0 | 0 |
| facts (raw) · catches the wrong fact | 42/42 (100.0%) | 0 | 0 |
| facts (raw) · no note on a right fact | 42/42 (100.0%) | 0 | 0 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 214/215 (99.5%) | 1 | 1 |
| facts (raw) · leak: note on a sentence that is not about facts | 200/215 (93.0%) | 15 | 1 |

- **Compliance verdict ready (red alert path):** p50 1069 · p95 1346 · max 1896 ms
- **Answer / prompter / switch verdict ready:** p50 1293 · p95 1469 · max 2040 ms
- **Fact verdict ready:** p50 1207 · p95 1717 · max 2266 ms
- **All done:** p50 1346 · p95 1781 · max 2266 ms
- **Timeouts:** {'fact checker': 1} of 300 each

## Wrong answers (case: what came back × runs)
- **judge · leak: alert on a sentence with no compliance claim:** H052: [{'span': 'instant skin hydration increased by seventy percent', 'rule_id': 'BRAND-SUPERLATIVE', 'severity': 'MEDIUM', 'is_negated': False, 'is_ ×1; H064: [{'span': 'forty-five percent', 'rule_id': 'ASEAN-3-SKIN-AGEING', 'severity': 'HIGH', 'is_negated': False, 'is_quoted': False, 'say_instead': 'D ×1; H064: [{'span': 'forty-five percent hydration boost', 'rule_id': 'BRAND-SUPERLATIVE', 'severity': 'MEDIUM', 'is_negated': False, 'is_quoted': False, ' ×1; H052: [{'span': 'increase by seventy percent right after one application', 'rule_id': 'ASEAN-DP5-PHYSIOLOGICAL', 'severity': 'HIGH', 'is_negated': Fal ×1; H053: [{'span': 'Corneometer readings showed skin hydration jumped thirty-eight percent right after applying', 'rule_id': 'BRAND-SUPERLATIVE', 'severi ×1; H064: [{'span': 'instant forty-five percent hydration boost', 'rule_id': 'BRAND-SUPERLATIVE', 'severity': 'MEDIUM', 'is_negated': False, 'is_quoted':  ×1
- **facts (after quote check) · leak: note on a sentence that is not about facts:** H092: [{'span': 'lightweight texture that suits oily skin', 'field': 'texture', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'lightweight t ×1
- **facts (raw) · leak: note on a sentence that is not about facts:** H007: [{'span': 'totally safe for expecting mothers', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value': 'totally safe', 'verdict' ×2; H004: [{'span': 'moisture retention is permanent', 'field': 'test_result', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'permanent', 'verdi ×1; H007: [{'span': 'totally safe for expecting mothers', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value': 'totally safe for pregnan ×1; H009: [{'span': 'bleaches out stubborn melanin so your face turns fairer within days', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stat ×1; H016: [{'span': 'stop your skin ageing process in its tracks', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'stops skin a ×1; H020: [{'span': 'whiten your dull skin tone and turn your complexion snow white', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_va ×1
