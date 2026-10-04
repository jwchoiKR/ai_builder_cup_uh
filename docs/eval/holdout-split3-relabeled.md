# Utterance agents · split3 · 2026-10-05

- **Agents:** ComplianceJudge + ContextJudge + FactChecker in parallel (production, D-099), on `gemini-3.5-flash-lite` (thinking MINIMAL).
- **Runs:** 100 eval cases × 3 runs = 300 case runs; every run scored. Timeouts are counted apart from wrong answers.
- **Script:** `backend/scripts/eval_agents.py`; production prompts in `prompts/`, the router prompt in `backend/scripts/experiments/prompts/`. Judge outputs get the production `post_validate`.

| Check | Correct / answered | Wrong | Timeout |
|---|---|---|---|
| judge · catches the violation (right rule) | 75/75 (100.0%) | 0 | 0 |
| judge · correction | 18/18 (100.0%) | 0 | 0 |
| judge · no alert on negated/quoted/approved wording | 29/30 (96.7%) | 1 | 0 |
| judge · leak: alert on a sentence with no compliance claim | 191/195 (97.9%) | 4 | 0 |
| judge · answer linking | 69/69 (100.0%) | 0 | 0 |
| judge · prompter points | 57/57 (100.0%) | 0 | 0 |
| judge · switch | 24/24 (100.0%) | 0 | 0 |
| facts (after quote check) · catches the wrong fact | 39/42 (92.9%) | 3 | 0 |
| facts (after quote check) · no note on a right fact | 42/42 (100.0%) | 0 | 0 |
| facts (raw) · catches the wrong fact | 42/42 (100.0%) | 0 | 0 |
| facts (raw) · no note on a right fact | 42/42 (100.0%) | 0 | 0 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 215/216 (99.5%) | 1 | 0 |
| facts (raw) · leak: note on a sentence that is not about facts | 172/216 (79.6%) | 44 | 0 |

- **Compliance verdict ready (red alert path):** p50 1046 · p95 1270 · max 1458 ms
- **Answer / prompter / switch verdict ready:** p50 1220 · p95 1401 · max 1641 ms
- **Fact verdict ready:** p50 1191 · p95 1599 · max 1973 ms
- **All done:** p50 1291 · p95 1601 · max 1973 ms
- **Timeouts:** none of 300 each

## Wrong answers (case: what came back × runs)
- **judge · no alert on negated/quoted/approved wording:** H032: [{'span': 'zero out of thirty-two participants reported irritation', 'rule_id': 'BRAND-ABSOLUTE-SAFETY', 'severity': 'MEDIUM', 'is_negated': Fal ×1
- **judge · leak: alert on a sentence with no compliance claim:** H064: [{'span': 'forty-five percent hydration boost', 'rule_id': 'BRAND-SUPERLATIVE', 'severity': 'MEDIUM', 'is_negated': False, 'is_quoted': False, ' ×2; H059: [{'span': 'zero out of thirty-two subjects had any adverse reaction', 'rule_id': 'BRAND-ABSOLUTE-SAFETY', 'severity': 'MEDIUM', 'is_negated': Fa ×1; H076: [{'span': 'a slight brief sensation is normal due to active niacinamide', 'rule_id': 'ASEAN-3-SKIN-NUMBING', 'severity': 'HIGH', 'is_negated': F ×1
- **facts (after quote check) · catches the wrong fact:** H046: [] ×3
- **facts (after quote check) · leak: note on a sentence that is not about facts:** H034: [{'span': 'rich texture', 'field': 'texture', 'product_id': 'cream_hydra_barrier', 'stated_value': 'rich', 'verdict': 'contradicted', 'correct_v ×1
- **facts (raw) · leak: note on a sentence that is not about facts:** H004: [{'span': 'the moisture retention is permanent', 'field': 'test_result', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'permanent', 'v ×2; H002: [{'span': 'guarantee you will never see another acne breakout again', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value':  ×2; H016: [{'span': 'stop your skin ageing process in its tracks', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'stops skin a ×2; H001: [{'span': 'this cream completely cures the inflammation', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value': 'cures inflamma ×1; H002: [{'span': 'guarantee you will never see another acne breakout again', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value':  ×1; H005: [{'span': 'physically reactivates your dormant skin cells to regenerate fresh tissue', 'field': 'other', 'product_id': 'ampoule_deep_hydration', ×1
