# Holdout sequences

36 sequence runs; 102 turns.
Gaps follow each final; inference overlaps. Each verdict is scored against that turn's labels.
State is captured after each turn's ordered context application, before later context applies.
Supported/none facts require no contradicted note. Missing agent results count as failures/timeouts.
Compliance, fact notes, corrections, coverage and answer links are scored from runtime effects; raw model outputs remain in JSON.
Read-out group matching and answer consistency are model context labels. AI PD model calls are disabled in this utterance evaluation.
Speech-end (injected final) to first active server alert: p50 1352 ms · p95 1532 ms · max 1563 ms (n=18).
STT and browser rendering are excluded. Provisional chips are excluded; later resolution preserves latency.

| Sequence | Turn | Correct | Wrong | Non-ok | Alert ms |
|---|---|---|---|---|---|
| S01 run 1 | 1 | 2 | 0 | 0 | 1531 |
| S01 run 1 | 2 | 3 | 0 | 0 | none |
| S01 run 1 | 3 | 3 | 0 | 0 | none |
| S02 run 1 | 1 | 2 | 0 | 0 | 1438 |
| S02 run 1 | 2 | 4 | 0 | 0 | none |
| S03 run 1 | 1 | 2 | 0 | 0 | 1469 |
| S03 run 1 | 2 | 2 | 0 | 0 | none |
| S03 run 1 | 3 | 2 | 0 | 0 | none |
| S04 run 1 | 1 | 3 | 0 | 0 | none |
| S04 run 1 | 2 | 2 | 1 | 0 | none |
| S04 run 1 | 3 | 4 | 0 | 0 | none |
| S05 run 1 | 1 | 4 | 0 | 0 | none |
| S05 run 1 | 2 | 5 | 0 | 0 | none |
| S06 run 1 | 1 | 2 | 0 | 0 | none |
| S06 run 1 | 2 | 3 | 0 | 0 | none |
| S07 run 1 | 1 | 2 | 0 | 0 | none |
| S07 run 1 | 2 | 2 | 0 | 0 | none |
| S07 run 1 | 3 | 3 | 0 | 0 | none |
| S08 run 1 | 1 | 2 | 0 | 0 | 1204 |
| S08 run 1 | 2 | 2 | 0 | 0 | none |
| S08 run 1 | 3 | 2 | 0 | 0 | none |
| S08 run 1 | 4 | 3 | 0 | 0 | none |
| S09 run 1 | 1 | 3 | 0 | 0 | none |
| S09 run 1 | 2 | 3 | 0 | 0 | none |
| S09 run 1 | 3 | 3 | 0 | 0 | none |
| S10 run 1 | 1 | 2 | 0 | 0 | none |
| S10 run 1 | 2 | 2 | 0 | 0 | 1219 |
| S10 run 1 | 3 | 2 | 0 | 0 | none |
| S11 run 1 | 1 | 4 | 0 | 0 | none |
| S11 run 1 | 2 | 3 | 0 | 0 | none |
| S11 run 1 | 3 | 5 | 0 | 0 | none |
| S12 run 1 | 1 | 2 | 0 | 0 | none |
| S12 run 1 | 2 | 2 | 0 | 0 | 1219 |
| S12 run 1 | 3 | 4 | 0 | 0 | none |
| S01 run 2 | 1 | 2 | 0 | 0 | 1563 |
| S01 run 2 | 2 | 3 | 0 | 0 | none |
| S01 run 2 | 3 | 3 | 0 | 0 | none |
| S02 run 2 | 1 | 2 | 0 | 0 | 1250 |
| S02 run 2 | 2 | 4 | 0 | 0 | none |
| S03 run 2 | 1 | 2 | 0 | 0 | 1344 |
| S03 run 2 | 2 | 2 | 0 | 0 | none |
| S03 run 2 | 3 | 2 | 0 | 0 | none |
| S04 run 2 | 1 | 3 | 0 | 0 | none |
| S04 run 2 | 2 | 2 | 1 | 0 | none |
| S04 run 2 | 3 | 4 | 0 | 0 | none |
| S05 run 2 | 1 | 4 | 0 | 0 | none |
| S05 run 2 | 2 | 5 | 0 | 0 | none |
| S06 run 2 | 1 | 2 | 0 | 0 | none |
| S06 run 2 | 2 | 3 | 0 | 0 | none |
| S07 run 2 | 1 | 2 | 0 | 0 | none |
| S07 run 2 | 2 | 2 | 0 | 0 | none |
| S07 run 2 | 3 | 3 | 0 | 0 | none |
| S08 run 2 | 1 | 2 | 0 | 0 | 1281 |
| S08 run 2 | 2 | 2 | 0 | 0 | none |
| S08 run 2 | 3 | 2 | 0 | 0 | none |
| S08 run 2 | 4 | 3 | 0 | 0 | none |
| S09 run 2 | 1 | 3 | 0 | 0 | none |
| S09 run 2 | 2 | 3 | 0 | 0 | none |
| S09 run 2 | 3 | 3 | 0 | 0 | none |
| S10 run 2 | 1 | 2 | 0 | 0 | none |
| S10 run 2 | 2 | 2 | 0 | 0 | 1171 |
| S10 run 2 | 3 | 2 | 0 | 0 | none |
| S11 run 2 | 1 | 4 | 0 | 0 | none |
| S11 run 2 | 2 | 3 | 0 | 0 | none |
| S11 run 2 | 3 | 5 | 0 | 0 | none |
| S12 run 2 | 1 | 2 | 0 | 0 | none |
| S12 run 2 | 2 | 2 | 0 | 0 | 1141 |
| S12 run 2 | 3 | 4 | 0 | 0 | none |
| S01 run 3 | 1 | 2 | 0 | 0 | 1406 |
| S01 run 3 | 2 | 3 | 0 | 0 | none |
| S01 run 3 | 3 | 2 | 1 | 0 | none |
| S02 run 3 | 1 | 2 | 0 | 0 | 1391 |
| S02 run 3 | 2 | 4 | 0 | 0 | none |
| S03 run 3 | 1 | 2 | 0 | 0 | 1532 |
| S03 run 3 | 2 | 2 | 0 | 0 | none |
| S03 run 3 | 3 | 2 | 0 | 0 | none |
| S04 run 3 | 1 | 3 | 0 | 0 | none |
| S04 run 3 | 2 | 2 | 1 | 0 | none |
| S04 run 3 | 3 | 4 | 0 | 0 | none |
| S05 run 3 | 1 | 4 | 0 | 0 | none |
| S05 run 3 | 2 | 5 | 0 | 0 | none |
| S06 run 3 | 1 | 2 | 0 | 0 | none |
| S06 run 3 | 2 | 3 | 0 | 0 | none |
| S07 run 3 | 1 | 2 | 0 | 0 | none |
| S07 run 3 | 2 | 2 | 0 | 0 | none |
| S07 run 3 | 3 | 3 | 0 | 0 | none |
| S08 run 3 | 1 | 2 | 0 | 0 | 1421 |
| S08 run 3 | 2 | 2 | 0 | 0 | none |
| S08 run 3 | 3 | 2 | 0 | 0 | none |
| S08 run 3 | 4 | 3 | 0 | 0 | none |
| S09 run 3 | 1 | 3 | 0 | 0 | none |
| S09 run 3 | 2 | 3 | 0 | 0 | none |
| S09 run 3 | 3 | 3 | 0 | 0 | none |
| S10 run 3 | 1 | 2 | 0 | 0 | none |
| S10 run 3 | 2 | 2 | 0 | 0 | 1172 |
| S10 run 3 | 3 | 2 | 0 | 0 | none |
| S11 run 3 | 1 | 4 | 0 | 0 | none |
| S11 run 3 | 2 | 3 | 0 | 0 | none |
| S11 run 3 | 3 | 4 | 0 | 1 | none |
| S12 run 3 | 1 | 2 | 0 | 0 | none |
| S12 run 3 | 2 | 1 | 0 | 1 | 1360 |
| S12 run 3 | 3 | 4 | 0 | 0 | none |

Checks: 279 correct; 4 wrong; 2 non-ok.
