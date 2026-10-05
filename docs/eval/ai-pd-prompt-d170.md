# AI PD arms: latency and agreement

12 cases (`pd_cases.jsonl`) × 3 runs per arm and path; no deadline while measuring; deadline in production 4000 ms.

| model | thinking | path | p50 | p95 | over deadline | gold | rule (gold is a card) | invalid/failed |
|---|---|---|---|---|---|---|---|---|
| gemini-3.8-flash | LOW | adk | 2082 ms | 2875 ms | 0/36 | 34/36 | 25/30 | 0 |

Misses against the gold (case: answers over the runs):

- gemini-3.8-flash LOW adk: PD12 → none, none
