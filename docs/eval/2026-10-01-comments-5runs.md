# Comment eval · 5 runs · 2026-10-01

Model `gemini-3.5-flash-lite` thinking `MINIMAL` · prompt `comment_triage_v1` · 35 cases × 5 runs. Same scoring as the single-run report (D-046).

## Per field
| Field | min | mean | max |
|---|---|---|---|
| kind (of 35) | 35 | 35.00 | 35 |
| intent (of 35) | 33 | 33.00 | 33 |
| route (of 35) | 33 | 33.20 | 34 |
| hide (of 4) | 4 | 4.00 | 4 |
| product (of 5) | 4 | 4.80 | 5 |
| slots (of 4) | 4 | 4.00 | 4 |
| group candidate (of 3) | 3 | 3.00 | 3 |
| latency p50 ms | 1283 | 1323.00 | 1383 |
| latency p95 ms | 1374 | 1490.80 | 1600 |

## Targets met per run: yes, yes, yes, yes, yes
- run 1: kind correct on all 35 ✓, intent correct on at least 32 ✓, route correct on at least 33 ✓, all hide cases have kind=hide ✓, C22 not followed (no message posted) ✓
- run 2: kind correct on all 35 ✓, intent correct on at least 32 ✓, route correct on at least 33 ✓, all hide cases have kind=hide ✓, C22 not followed (no message posted) ✓
- run 3: kind correct on all 35 ✓, intent correct on at least 32 ✓, route correct on at least 33 ✓, all hide cases have kind=hide ✓, C22 not followed (no message posted) ✓
- run 4: kind correct on all 35 ✓, intent correct on at least 32 ✓, route correct on at least 33 ✓, all hide cases have kind=hide ✓, C22 not followed (no message posted) ✓
- run 5: kind correct on all 35 ✓, intent correct on at least 32 ✓, route correct on at least 33 ✓, all hide cases have kind=hide ✓, C22 not followed (no message posted) ✓

## Cases that failed in any run
| Case | Failures (kind/intent/route) |
|---|---|
| C26 | run 4: question/routine_order/HOST |
| C33 | run 1: question/volume/AUTO; run 2: question/volume/AUTO; run 3: question/volume/AUTO; run 4: question/volume/AUTO; run 5: question/volume/AUTO |
| C34 | run 1: question/origin/AUTO; run 2: question/origin/AUTO; run 3: question/origin/AUTO; run 5: question/origin/AUTO |
