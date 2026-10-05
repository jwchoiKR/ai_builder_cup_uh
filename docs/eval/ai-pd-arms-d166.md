# AI PD arms: latency and agreement

12 cases (`pd_cases.jsonl`) × 3 runs per arm and path; no deadline while measuring; deadline in production 4000 ms.

| model | thinking | path | p50 | p95 | over deadline | gold | rule (gold is a card) | invalid/failed |
|---|---|---|---|---|---|---|---|---|
| gemini-3.8-flash | LOW | adk | 2139 ms | 3724 ms | 2/36 | 36/36 | 27/30 | 0 |
| gemini-3.8-flash | LOW | direct | 2186 ms | 5631 ms | 3/36 | 30/36 | 27/30 | 0 |
| gemini-3.5-flash-lite | MINIMAL | adk | 994 ms | 1185 ms | 0/36 | 25/36 | 19/30 | 0 |
| gemini-3.5-flash-lite | MINIMAL | direct | 959 ms | 1053 ms | 0/36 | 25/36 | 18/30 | 0 |

Misses against the gold (case: answers over the runs):

- gemini-3.8-flash LOW direct: PD09 → question:g_size, question:g_size, question:g_size; PD12 → none, none, none
- gemini-3.5-flash-lite MINIMAL adk: PD04 → question:g_size, question:g_size, question:g_size; PD06 → switch:ampoule_deep_hydration:cr-p3, switch:ampoule_deep_hydration:cr-p3, switch:ampoule_deep_hydration:cr-p3; PD07 → switch:ampoule_deep_hydration, switch:ampoule_deep_hydration, switch:ampoule_deep_hydration; PD12 → none, none
- gemini-3.5-flash-lite MINIMAL direct: PD04 → question:g_size, question:g_size; PD06 → switch:ampoule_deep_hydration:cr-p3, switch:ampoule_deep_hydration:cr-p3, switch:ampoule_deep_hydration:cr-p3; PD07 → switch:ampoule_deep_hydration, switch:ampoule_deep_hydration, switch:ampoule_deep_hydration; PD12 → none, none, none
