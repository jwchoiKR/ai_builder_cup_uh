# Utterance agents baseline (split, 2 agents) · 2026-10-02

**What runs:**
- The 39 utterance eval cases (`data/eval/utterance_cases.jsonl`), text in as the final transcript.
- The real UtteranceJudge and FactChecker on `gemini-3.5-flash-lite` (thinking MINIMAL), called in parallel, deadlines 2500 / 3000 ms.
- 20 runs, so 780 case runs, 6 cases at a time (12 calls in flight). Every run is scored.
- No orchestrator code: the agents' outputs are scored directly.
- The fact checker is scored twice: its raw model answer, and after its own quote check (`post_validate`).
- Script: `backend/scripts/eval_agents.py` (`--from-json` re-scores saved outputs).

**Leak** means an agent answering in the other agent's area:
- judge: a compliance alert on a sentence with no compliance claim (prices, facts, answers, transitions);
- fact checker: a "wrong fact" note on a sentence that is not about facts (compliance claims, answers, transitions).

**Accuracy** is over the runs where the agent answered in time; timeouts are counted separately.

## Accuracy
| Check | Correct / answered | Wrong | Timeout |
|---|---|---|---|
| judge · answer linking | 78/78 (100.0%) | 0 | 2 |
| judge · catches the violation (right rule) | 251/251 (100.0%) | 0 | 9 |
| judge · correction | 20/20 (100.0%) | 0 | 0 |
| judge · no alert on negated/quoted/approved wording | 115/115 (100.0%) | 0 | 5 |
| judge · prompter points | 76/76 (100.0%) | 0 | 4 |
| judge · switch | 79/79 (100.0%) | 0 | 1 |
| judge · leak: alert on a sentence with no compliance claim | 386/387 (99.7%) | 1 | 13 |
| facts (after quote check) · catches the wrong fact | 80/80 (100.0%) | 0 | 0 |
| facts (after quote check) · no note on a right fact | 119/119 (100.0%) | 0 | 1 |
| facts (raw) · catches the wrong fact | 80/80 (100.0%) | 0 | 0 |
| facts (raw) · no note on a right fact | 119/119 (100.0%) | 0 | 1 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 544/570 (95.4%) | 26 | 10 |
| facts (raw) · leak: note on a sentence that is not about facts | 474/570 (83.2%) | 96 | 10 |

## Latency (each agent, and both done = the slower of the two)
- **Judge:** p50 1506 ms · p95 1826 ms · max 2498 ms
- **Fact checker:** p50 1301 ms · p95 1782 ms · max 2595 ms
- **Both done:** p50 1536 ms · p95 1931 ms · max 2595 ms
- **Statuses:** {'judge ok': 753, 'judge timeout': 27, 'facts ok': 769, 'facts timeout': 11}

## Wrong answers (case: what came back × runs)
- **judge · leak: alert on a sentence with no compliance claim:** U21: got ASEAN-DP5-PHYSIOLOGICAL ×1
- **facts (after quote check) · leak: note on a sentence that is not about facts:** U09: got test_result: 2 weeks -> 4 weeks ×11; U10: got other: prescription cream -> cosmetic product ×11; U09: got other: 2 weeks -> 4 weeks ×1; U11: got other: ten years younger -> Cosmetic effects only ×1; U07: got other: safe for pregnant women -> not specifically tested on pregnant or breastfeeding women; consult doctor before use ×1; U09: got other: whitens in two weeks -> Participants who said skin looked more radiant after 4 weeks: 26 of 30 (87%) ×1
- **facts (raw) · leak: note on a sentence that is not about facts:** U06: got other: removes acne scars -> Treats acne, acne scars, pigmentation disorders or any skin disease. ×15; U09: got test_result: 2 weeks -> 4 weeks ×11; U10: got other: prescription cream -> cosmetic product ×11; U05: got other: Regenerates skin cells -> Claims not approved: Removes wrinkles or reverses skin ageing. Whitens skin, or permanently changes skin colour. Treat ×5; U05: got other: Regenerates skin cells -> Claims not approved: Repairs, heals or regenerates skin cells. ×4; U10: got other: prescription cream -> Not a medicine or a prescription product ×4; U03: got other: treats acne -> Claims not approved: Removes wrinkles or reverses skin ageing. Whitens skin, or permanently changes skin colour. Treats acne, acn ×4; U10: got other: prescription cream -> not a medicine or prescription product ×3
