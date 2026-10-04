# Holdout sequences

36 sequence runs; 102 turns.
Gaps follow each final; inference overlaps. Each verdict is scored against that turn's labels.
State is captured after each turn's ordered context application, before later context applies.
Supported/none facts require no contradicted note. Missing agent results count as failures/timeouts.
Compliance, fact notes, corrections, coverage and answer links are scored from runtime effects; raw model outputs remain in JSON.
Read-out group matching and answer consistency are model context labels. AI PD model calls are disabled in this utterance evaluation.
Speech-end (injected final) to first active server alert: p50 1250 ms · p95 1390 ms · max 1593 ms (n=18).
STT and browser rendering are excluded. Provisional chips are excluded; later resolution preserves latency.

| Sequence | Turn | Correct | Wrong | Non-ok | Alert ms |
|---|---|---|---|---|---|
| S01 run 1 | 1 | 2 | 0 | 0 | 1375 |
| S01 run 1 | 2 | 3 | 0 | 0 | none |
| S01 run 1 | 3 | 3 | 0 | 0 | none |
| S02 run 1 | 1 | 2 | 0 | 0 | 1219 |
| S02 run 1 | 2 | 3 | 0 | 1 | none |
| S03 run 1 | 1 | 2 | 0 | 0 | 1593 |
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
| S08 run 1 | 1 | 2 | 0 | 0 | 1171 |
| S08 run 1 | 2 | 2 | 0 | 0 | none |
| S08 run 1 | 3 | 2 | 0 | 0 | none |
| S08 run 1 | 4 | 2 | 1 | 0 | none |
| S09 run 1 | 1 | 3 | 0 | 0 | none |
| S09 run 1 | 2 | 3 | 0 | 0 | none |
| S09 run 1 | 3 | 3 | 0 | 0 | none |
| S10 run 1 | 1 | 2 | 0 | 0 | none |
| S10 run 1 | 2 | 2 | 0 | 0 | 1172 |
| S10 run 1 | 3 | 2 | 0 | 0 | none |
| S11 run 1 | 1 | 4 | 0 | 0 | none |
| S11 run 1 | 2 | 3 | 0 | 0 | none |
| S11 run 1 | 3 | 5 | 0 | 0 | none |
| S12 run 1 | 1 | 2 | 0 | 0 | none |
| S12 run 1 | 2 | 2 | 0 | 0 | 1280 |
| S12 run 1 | 3 | 4 | 0 | 0 | none |
| S01 run 2 | 1 | 2 | 0 | 0 | 1172 |
| S01 run 2 | 2 | 3 | 0 | 0 | none |
| S01 run 2 | 3 | 2 | 1 | 0 | none |
| S02 run 2 | 1 | 2 | 0 | 0 | 1078 |
| S02 run 2 | 2 | 4 | 0 | 0 | none |
| S03 run 2 | 1 | 2 | 0 | 0 | 1218 |
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
| S08 run 2 | 1 | 2 | 0 | 0 | 1344 |
| S08 run 2 | 2 | 2 | 0 | 0 | none |
| S08 run 2 | 3 | 2 | 0 | 0 | none |
| S08 run 2 | 4 | 2 | 1 | 0 | none |
| S09 run 2 | 1 | 3 | 0 | 0 | none |
| S09 run 2 | 2 | 3 | 0 | 0 | none |
| S09 run 2 | 3 | 3 | 0 | 0 | none |
| S10 run 2 | 1 | 2 | 0 | 0 | none |
| S10 run 2 | 2 | 2 | 0 | 0 | 1266 |
| S10 run 2 | 3 | 2 | 0 | 0 | none |
| S11 run 2 | 1 | 4 | 0 | 0 | none |
| S11 run 2 | 2 | 3 | 0 | 0 | none |
| S11 run 2 | 3 | 5 | 0 | 0 | none |
| S12 run 2 | 1 | 2 | 0 | 0 | none |
| S12 run 2 | 2 | 2 | 0 | 0 | 1234 |
| S12 run 2 | 3 | 4 | 0 | 0 | none |
| S01 run 3 | 1 | 2 | 0 | 0 | 1375 |
| S01 run 3 | 2 | 3 | 0 | 0 | none |
| S01 run 3 | 3 | 3 | 0 | 0 | none |
| S02 run 3 | 1 | 2 | 0 | 0 | 1157 |
| S02 run 3 | 2 | 4 | 0 | 0 | none |
| S03 run 3 | 1 | 2 | 0 | 0 | 1390 |
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
| S08 run 3 | 1 | 2 | 0 | 0 | 1282 |
| S08 run 3 | 2 | 2 | 0 | 0 | none |
| S08 run 3 | 3 | 2 | 0 | 0 | none |
| S08 run 3 | 4 | 2 | 1 | 0 | none |
| S09 run 3 | 1 | 3 | 0 | 0 | none |
| S09 run 3 | 2 | 3 | 0 | 0 | none |
| S09 run 3 | 3 | 3 | 0 | 0 | none |
| S10 run 3 | 1 | 2 | 0 | 0 | none |
| S10 run 3 | 2 | 2 | 0 | 0 | 1125 |
| S10 run 3 | 3 | 2 | 0 | 0 | none |
| S11 run 3 | 1 | 4 | 0 | 0 | none |
| S11 run 3 | 2 | 3 | 0 | 0 | none |
| S11 run 3 | 3 | 5 | 0 | 0 | none |
| S12 run 3 | 1 | 2 | 0 | 0 | none |
| S12 run 3 | 2 | 2 | 0 | 0 | 1343 |
| S12 run 3 | 3 | 4 | 0 | 0 | none |

Checks: 277 correct; 7 wrong; 1 non-ok.
