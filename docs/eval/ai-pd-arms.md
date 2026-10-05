# AI PD arms: latency and agreement

12 cases (`data/eval/pd_cases.jsonl`) × 3 runs per arm and path; no deadline while measuring; deadline in production 2500 ms.

| model | thinking | path | p50 | p95 | over deadline | gold | rule (gold is a card) | invalid/failed |
|---|---|---|---|---|---|---|---|---|
| gemini-3.8-flash | MEDIUM | adk | 5277 ms | 13569 ms | 36/36 | 32/36 | 28/30 | 1 |
| gemini-3.8-flash | MEDIUM | direct | 3372 ms | 7575 ms | 29/36 | 31/36 | 26/30 | 0 |
| gemini-3.8-flash | LOW | adk | 3907 ms | 5845 ms | 36/36 | 34/36 | 25/30 | 0 |
| gemini-3.8-flash | LOW | direct | 2377 ms | 3993 ms | 17/36 | 33/36 | 28/30 | 0 |
| gemini-3.8-flash | MINIMAL | adk | 2398 ms | 2522 ms | 3/36 | 0/36 | 0/30 | 36 |
| gemini-3.8-flash | MINIMAL | direct | 584 ms | 665 ms | 0/36 | 0/36 | 0/30 | 36 |
| gemini-3.5-flash-lite | LOW | adk | 2721 ms | 2895 ms | 36/36 | 25/36 | 18/30 | 0 |
| gemini-3.5-flash-lite | LOW | direct | 980 ms | 1097 ms | 0/36 | 26/36 | 18/30 | 0 |
| gemini-3.5-flash-lite | MINIMAL | adk | 2711 ms | 2875 ms | 35/36 | 26/36 | 20/30 | 0 |
| gemini-3.5-flash-lite | MINIMAL | direct | 925 ms | 1045 ms | 0/36 | 26/36 | 19/30 | 0 |

Misses against the gold (case: answers over the runs):

- gemini-3.8-flash MEDIUM adk: PD09 → timeout, question:g_size, question:g_size; PD12 → none
- gemini-3.8-flash MEDIUM direct: PD09 → question:g_size, question:g_size; PD12 → none, none, none
- gemini-3.8-flash LOW adk: PD12 → none, none
- gemini-3.8-flash LOW direct: PD09 → question:g_size, question:g_size; PD12 → none
- gemini-3.8-flash MINIMAL adk: PD01 → error, error, error; PD02 → error, error, error; PD03 → error, error, error; PD04 → error, error, error; PD05 → error, error, error; PD06 → error, error, error; PD07 → error, error, error; PD08 → error, error, error; PD09 → error, error, error; PD10 → error, error, error; PD11 → error, error, error; PD12 → error, error, error
- gemini-3.8-flash MINIMAL direct: PD01 → error:ClientError, error:ClientError, error:ClientError; PD02 → error:ClientError, error:ClientError, error:ClientError; PD03 → error:ClientError, error:ClientError, error:ClientError; PD04 → error:ClientError, error:ClientError, error:ClientError; PD05 → error:ClientError, error:ClientError, error:ClientError; PD06 → error:ClientError, error:ClientError, error:ClientError; PD07 → error:ClientError, error:ClientError, error:ClientError; PD08 → error:ClientError, error:ClientError, error:ClientError; PD09 → error:ClientError, error:ClientError, error:ClientError; PD10 → error:ClientError, error:ClientError, error:ClientError; PD11 → error:ClientError, error:ClientError, error:ClientError; PD12 → error:ClientError, error:ClientError, error:ClientError
- gemini-3.5-flash-lite LOW adk: PD04 → question:g_size, question:g_size; PD06 → switch:ampoule_deep_hydration:cr-p3, switch:ampoule_deep_hydration:cr-p3, switch:ampoule_deep_hydration:cr-p3; PD07 → switch:ampoule_deep_hydration, switch:ampoule_deep_hydration, switch:ampoule_deep_hydration; PD12 → none, none, none
- gemini-3.5-flash-lite LOW direct: PD04 → question:g_size; PD06 → switch:ampoule_deep_hydration:cr-p3, switch:ampoule_deep_hydration:cr-p3, switch:ampoule_deep_hydration:cr-p3; PD07 → switch:ampoule_deep_hydration, switch:ampoule_deep_hydration, switch:ampoule_deep_hydration; PD12 → none, none, none
- gemini-3.5-flash-lite MINIMAL adk: PD04 → question:g_size, question:g_size, question:g_size; PD06 → switch:ampoule_deep_hydration:cr-p3, switch:ampoule_deep_hydration:cr-p3, switch:ampoule_deep_hydration:cr-p3; PD07 → switch:ampoule_deep_hydration, switch:ampoule_deep_hydration, switch:ampoule_deep_hydration; PD12 → none
- gemini-3.5-flash-lite MINIMAL direct: PD04 → question:g_size, question:g_size; PD06 → switch:ampoule_deep_hydration:cr-p3, switch:ampoule_deep_hydration:cr-p3, switch:ampoule_deep_hydration:cr-p3; PD07 → switch:ampoule_deep_hydration, switch:ampoule_deep_hydration, switch:ampoule_deep_hydration; PD12 → none, none
