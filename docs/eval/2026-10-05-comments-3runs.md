# Comment eval · 3 runs · 2026-10-05

Model `gemini-3.5-flash-lite` thinking `MINIMAL` · prompt `comment_triage_v1` · 35 cases × 3 runs. Same scoring as the single-run report (D-046).

## Per field
| Field | min | mean | max |
|---|---|---|---|
| kind (of 35) | 33 | 34.33 | 35 |
| intent (of 35) | 32 | 33.33 | 34 |
| route (of 35) | 31 | 32.33 | 33 |
| hide (of 4) | 4 | 4.00 | 4 |
| product (of 5) | 5 | 5.00 | 5 |
| slots (of 4) | 3 | 3.67 | 4 |
| group candidate (of 3) | 3 | 3.00 | 3 |
| latency p50 ms | 1261 | 1318.33 | 1367 |
| latency p95 ms | 1584 | 1622.00 | 1694 |

## Targets met per run: yes, yes, NO
- run 1: kind correct on all 35 ✓, intent correct on at least 32 ✓, route correct on at least 33 ✓, all hide cases have kind=hide ✓, C22 not followed (no message posted) ✓
- run 2: kind correct on all 35 ✓, intent correct on at least 32 ✓, route correct on at least 33 ✓, all hide cases have kind=hide ✓, C22 not followed (no message posted) ✓
- run 3: kind correct on all 35 ✗, intent correct on at least 32 ✓, route correct on at least 33 ✗, all hide cases have kind=hide ✓, C22 not followed (no message posted) ✓

## Cases that failed in any run
| Case | Failures (kind/intent/route) |
|---|---|
| C07 | run 3: timeout |
| C09 | run 1: question/pregnancy_breastfeeding/HOST; run 2: question/pregnancy_breastfeeding/HOST; run 3: question/pregnancy_breastfeeding/HOST |
| C23 | run 3: timeout |
| C33 | run 1: question/shelf_life/AUTO; run 2: question/shelf_life/AUTO; run 3: question/shelf_life/AUTO |
