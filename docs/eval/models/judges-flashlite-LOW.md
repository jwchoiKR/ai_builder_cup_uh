# Utterance agents · split3 · 2026-10-05

- **Agents:** ComplianceJudge + ContextJudge + FactChecker in parallel (production, D-099), on `gemini-3.5-flash-lite` (thinking LOW).
- **Runs:** 100 eval cases × 3 runs = 300 case runs; every run scored. Timeouts are counted apart from wrong answers.
- **Script:** `backend/scripts/eval_agents.py`; production prompts in `prompts/`, the router prompt in `backend/scripts/experiments/prompts/`. Judge outputs get the production `post_validate`.

| Check | Correct / answered | Wrong | Timeout |
|---|---|---|---|
| judge · catches the violation (right rule) | 75/75 (100.0%) | 0 | 0 |
| judge · correction | 18/18 (100.0%) | 0 | 0 |
| judge · no alert on negated/quoted/approved wording | 30/30 (100.0%) | 0 | 0 |
| judge · leak: alert on a sentence with no compliance claim | 183/195 (93.8%) | 12 | 0 |
| judge · answer linking | 69/69 (100.0%) | 0 | 0 |
| judge · prompter points | 57/57 (100.0%) | 0 | 0 |
| judge · switch | 24/24 (100.0%) | 0 | 0 |
| facts (after quote check) · catches the wrong fact | 42/42 (100.0%) | 0 | 0 |
| facts (after quote check) · no note on a right fact | 42/42 (100.0%) | 0 | 0 |
| facts (raw) · catches the wrong fact | 42/42 (100.0%) | 0 | 0 |
| facts (raw) · no note on a right fact | 42/42 (100.0%) | 0 | 0 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 214/216 (99.1%) | 2 | 0 |
| facts (raw) · leak: note on a sentence that is not about facts | 204/216 (94.4%) | 12 | 0 |

- **Compliance verdict ready (red alert path):** p50 1086 · p95 1354 · max 1738 ms
- **Answer / prompter / switch verdict ready:** p50 1220 · p95 1462 · max 1896 ms
- **Fact verdict ready:** p50 1187 · p95 1750 · max 2313 ms
- **All done:** p50 1314 · p95 1767 · max 2313 ms
- **Timeouts:** none of 300 each

## Wrong answers (case: what came back × runs)
- **judge · leak: alert on a sentence with no compliance claim:** H052: [{'span': 'instant skin hydration increased by seventy percent right after one application', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MED ×3; H059: [{'span': 'zero out of thirty-two subjects had any adverse reaction', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': Fal ×3; H053: [{'span': 'Corneometer readings showed skin hydration jumped thirty-eight percent right after applying', 'rule_id': 'BRAND-TEST-QUALIFIER', 'sev ×2; H064: [{'span': 'forty-five percent hydration boost', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': False, 'is_quoted': False ×2; H064: [{'span': 'forty-five percent', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': False, 'is_quoted': False, 'say_instead': ×1; H053: [{'span': 'hydration jumped thirty-eight percent right after applying', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': F ×1
- **facts (after quote check) · leak: note on a sentence that is not about facts:** H072: [{'span': 'half a pump', 'field': 'usage', 'product_id': 'cream_hydra_barrier', 'stated_value': 'half a pump', 'verdict': 'contradicted', 'corre ×1; H072: [{'span': 'half a pump', 'field': 'usage', 'product_id': 'cream_hydra_barrier', 'stated_value': 'half a pump', 'verdict': 'contradicted', 'corre ×1
- **facts (raw) · leak: note on a sentence that is not about facts:** H004: [{'span': 'the moisture retention is permanent', 'field': 'test_result', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'permanent mois ×1; H007: [{'span': 'totally safe for expecting mothers', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value': 'totally safe', 'verdict' ×1; H016: [{'span': 'stop your skin ageing process in its tracks', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'stops aging' ×1; H004: [{'span': 'the moisture retention is permanent', 'field': 'test_result', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'permanent mois ×1; H007: [{'span': 'totally safe for expecting mothers', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value': 'totally safe for expecti ×1; H016: [{'span': 'stop your skin ageing process in its tracks', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'stops skin a ×1
