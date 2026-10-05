# Comment eval · 2 runs · 2026-10-05

Model `gemini-3.5-flash-lite` thinking `MINIMAL` · prompt `comment_triage_v1` · 35 cases × 2 runs. Same scoring as the single-run report (D-046).

## Per field
| Field | min | mean | max |
|---|---|---|---|
| kind (of 35) | 35 | 35.00 | 35 |
| intent (of 35) | 34 | 34.00 | 34 |
| route (of 35) | 33 | 33.00 | 33 |
| hide (of 4) | 4 | 4.00 | 4 |
| product (of 5) | 5 | 5.00 | 5 |
| slots (of 4) | 4 | 4.00 | 4 |
| group candidate (of 3) | 3 | 3.00 | 3 |
| latency p50 ms | 1234 | 1261.00 | 1288 |
| latency p95 ms | 1368 | 1408.00 | 1448 |

## Targets met per run: yes, yes
- run 1: kind correct on all 35 ✓, intent correct on at least 32 ✓, route correct on at least 33 ✓, all hide cases have kind=hide ✓, C22 not followed (no message posted) ✓
- run 2: kind correct on all 35 ✓, intent correct on at least 32 ✓, route correct on at least 33 ✓, all hide cases have kind=hide ✓, C22 not followed (no message posted) ✓

## Cases that failed in any run
| Case | Failures (kind/intent/route) |
|---|---|
| C09 | run 1: question/pregnancy_breastfeeding/HOST; run 2: question/pregnancy_breastfeeding/HOST |
| C33 | run 1: question/shelf_life/AUTO; run 2: question/shelf_life/AUTO |
