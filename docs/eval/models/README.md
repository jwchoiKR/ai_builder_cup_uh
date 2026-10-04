# Fast-model comparison (10/5, commit 1f8b8d3, Vertex global, cache on)

Same sets for every model: judges = 100 unseen holdout cases x 3 runs (split3); triage = 35 comment cases x 3 runs.
Only `LLM_FAST_MODEL` changed (thinking MINIMAL). Latency measured from a PC in Korea to the global endpoint.

| fast model | violations caught | no alert on safe wording | wrong facts caught | compliance p50 / p95 (ms) | all judges p95 (ms) | triage intent / route (of 35, mean) | triage p95 (ms) |
|---|---|---|---|---|---|---|---|
| gemini-3.5-flash-lite (current) | 75/75 | 30/30 | 42/42 | 1074 / 1357 | 1750 | 32.7 / 32.3 | 1466 |
| gemini-3.1-flash-lite | 75/75 | 30/30 | 35/42 | 1785 / 2208 | 2571 | 33.0 / 33.0 | 2215 |
| gemini-3.5-flash | 75/75 | 30/30 | 39/42 | 1457 / 1819 | 2346 | 33.0 / 32.0 | 1951 |
| gemini-3.6-flash | 75/75 | 30/30 | 39/42 | 1568 / 1884 | 2637 | 33.0 / 33.0 | (see triage file) |

Result: keep gemini-3.5-flash-lite. It is the fastest and the only one that caught all 42 wrong facts.
The larger models missed packaging ("jar") and shelf-life facts (H078) and set price (H046), and are 0.4-0.9 s slower at p95 on the 3 s path.
gemini-3.7-flash and gemini-3.8-flash do not accept MINIMAL thinking; they were not tested on the 3 s path.
Not tested yet: the answer composer (gemini-3.8-flash LOW) against alternatives.

## Thinking levels with the models fixed (10/5, user direction: flash-lite = 3.5, flash = 3.8)

Holdout labels: H052, H053, H059 and H064 now expect BRAND-TEST-QUALIFIER (test results said without "in our in-house test", D-105); reports re-scored from the saved runs (`*-relabeled.md`).

| setting | violations caught | false compliance alerts (of 183) | fact notes on non-fact lines (of 216) | wrong facts caught | compliance p95 | all judges p95 |
|---|---|---|---|---|---|---|
| flash-lite MINIMAL (current) | 87/87 | 3 | 0 | 42/42 | 1357 ms | 1750 ms |
| flash-lite LOW | 87/87 | **0** | 2 | 42/42 | 1354 ms | 1767 ms |
| flash-lite MEDIUM | timeouts on the 3 s path (many calls cut at the deadline) | | | | 2353 ms | 2933 ms |

Adversarial tune set (80 x 3): MINIMAL and LOW both 100% detection, 0 wrong HIGH, 0% false alerts; MEDIUM 43.7% (timeouts).
Triage (35 x 3): LOW intent 34.0 / route 33.0 vs MINIMAL 32.7 / 32.3, same p95 (1444 vs 1466 ms).
Composer (gemini-3.8-flash): LOW vs MEDIUM, verify pass 74% vs 72%, p50 2.5 s vs 5.9 s: keep LOW (`composer-38flash-thinking.md`).

Recommendation: compliance judge LOW (0 false alerts, same speed), fact checker MINIMAL (no stray notes), triage LOW, composer LOW. This needs a per-agent thinking setting.
