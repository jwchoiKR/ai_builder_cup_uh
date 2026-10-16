# Routing accuracy

79 cases x 5 runs; deadlines jev: 500 ms, gemini_purpose: 1500 ms, llm: 500 ms, regex: no deadline; no retries; Jev threshold 0.05.

Legacy utterance labels follow the prescribed NEEDS lists. These label screen changes, not all semantically checkable facts. Additional cases use explicit labels.

Errors and timeouts fail open, including every threshold sweep. High recall can therefore coexist with a failed router; inspect status counts and calls saved. Warm-up is excluded.

Regex measures only facts; compliance and context are N/A. Its latency excludes the shared overrides.

Production findings: utterances.py serializes successive final utterances; fact-note publication depends on the _side path. This route-only experiment does not measure or change either behavior.

| Router | Status counts | p50 ms | p95 ms | max ms |
|---|---|---:|---:|---:|
| jev | {"ok": 395} | 205.000 | 275.000 | 481.000 |
| gemini_purpose | {"ok": 392, "timeout": 3} | 986.000 | 1213.000 | 1519.000 |
| llm | {"timeout": 395} | 507.000 | 520.000 | 529.000 |
| regex | {"ok": 395} | 0.015 | 0.031 | 0.049 |

| Router / sweep | Specialist | Recall | Precision | Calls saved | Misses (runs) | Case IDs |
|---|---|---:|---:|---:|---:|---|
| jev | compliance | 100.0% | 34.7% | 6/395 | 0 |  |
| jev | facts | 100.0% | 28.4% | 60/395 | 0 |  |
| jev | context | 100.0% | 35.2% | 11/395 | 0 |  |
| gemini_purpose | compliance | 100.0% | 81.3% | 229/395 | 0 |  |
| gemini_purpose | facts | 94.7% | 54.5% | 230/395 | 5 | R36 |
| gemini_purpose | context | 86.7% | 72.2% | 233/395 | 18 | R16, R17, R21, U34 |
| llm | compliance | 100.0% | 34.2% | 0/395 | 0 |  |
| llm | facts | 100.0% | 24.1% | 0/395 | 0 |  |
| llm | context | 100.0% | 34.2% | 0/395 | 0 |  |
| regex | compliance | N/A | N/A | N/A | N/A | |
| regex | facts | 100.0% | 36.5% | 135/395 | 0 |  |
| regex | context | N/A | N/A | N/A | N/A | |
| Jev 0.02 overrides on | compliance | 100.0% | 34.2% | 0/395 | 0 |  |
| Jev 0.02 overrides on | facts | 100.0% | 24.1% | 0/395 | 0 |  |
| Jev 0.02 overrides on | context | 100.0% | 34.2% | 0/395 | 0 |  |
| Jev 0.02 overrides off | compliance | 100.0% | 34.2% | 0/395 | 0 |  |
| Jev 0.02 overrides off | facts | 100.0% | 24.1% | 0/395 | 0 |  |
| Jev 0.02 overrides off | context | 100.0% | 34.2% | 0/395 | 0 |  |
| Jev 0.05 overrides on | compliance | 100.0% | 34.7% | 6/395 | 0 |  |
| Jev 0.05 overrides on | facts | 100.0% | 28.4% | 60/395 | 0 |  |
| Jev 0.05 overrides on | context | 100.0% | 35.2% | 11/395 | 0 |  |
| Jev 0.05 overrides off | compliance | 100.0% | 34.7% | 6/395 | 0 |  |
| Jev 0.05 overrides off | facts | 100.0% | 28.4% | 60/395 | 0 |  |
| Jev 0.05 overrides off | context | 100.0% | 35.2% | 11/395 | 0 |  |
| Jev 0.1 overrides on | compliance | 100.0% | 45.0% | 95/395 | 0 |  |
| Jev 0.1 overrides on | facts | 100.0% | 30.2% | 80/395 | 0 |  |
| Jev 0.1 overrides on | context | 100.0% | 37.0% | 30/395 | 0 |  |
| Jev 0.1 overrides off | compliance | 100.0% | 45.0% | 95/395 | 0 |  |
| Jev 0.1 overrides off | facts | 100.0% | 30.2% | 80/395 | 0 |  |
| Jev 0.1 overrides off | context | 100.0% | 37.0% | 30/395 | 0 |  |
| Jev 0.2 overrides on | compliance | 100.0% | 66.8% | 193/395 | 0 |  |
| Jev 0.2 overrides on | facts | 100.0% | 31.6% | 94/395 | 0 |  |
| Jev 0.2 overrides on | context | 100.0% | 42.9% | 80/395 | 0 |  |
| Jev 0.2 overrides off | compliance | 100.0% | 73.8% | 212/395 | 0 |  |
| Jev 0.2 overrides off | facts | 100.0% | 31.6% | 94/395 | 0 |  |
| Jev 0.2 overrides off | context | 100.0% | 42.9% | 80/395 | 0 |  |
| Jev 0.3 overrides on | compliance | 100.0% | 73.0% | 210/395 | 0 |  |
| Jev 0.3 overrides on | facts | 100.0% | 32.3% | 101/395 | 0 |  |
| Jev 0.3 overrides on | context | 100.0% | 59.5% | 168/395 | 0 |  |
| Jev 0.3 overrides off | compliance | 100.0% | 84.4% | 235/395 | 0 |  |
| Jev 0.3 overrides off | facts | 100.0% | 32.3% | 101/395 | 0 |  |
| Jev 0.3 overrides off | context | 100.0% | 59.5% | 168/395 | 0 |  |
| Jev 0.5 overrides on | compliance | 100.0% | 79.4% | 225/395 | 0 |  |
| Jev 0.5 overrides on | facts | 100.0% | 41.7% | 167/395 | 0 |  |
| Jev 0.5 overrides on | context | 90.4% | 65.2% | 208/395 | 13 | R17, R21, R40 |
| Jev 0.5 overrides off | compliance | 96.3% | 92.9% | 255/395 | 5 | U23 |
| Jev 0.5 overrides off | facts | 100.0% | 41.7% | 167/395 | 0 |  |
| Jev 0.5 overrides off | context | 90.4% | 65.2% | 208/395 | 13 | R17, R21, R40 |
