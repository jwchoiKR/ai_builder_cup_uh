# Why run P's fact checker took 31.5 s at p95

Run P (the deployed setting) gave a fact checker p95 of 31.5 s on set 10. Runs C and D on the same lines gave 5.4 and 6.2 s. The cause is on Gemini's side: that night, Gemini 3.8 Flash returned many 504 errors and answered slowly. Our requests did not change.

## What the stored results show

`python eval/sealed_set_10/fact_latency.py` prints this from `results/pool10/`:

| Run | Fact calls ok | p50 | p95 | Max | Timed out | Input tokens per call |
|---|---|---|---|---|---|---|
| P | 249 | 6.0 s | 29.3 s | 53.4 s | 26 | 5,067-6,007 |
| B | 272 | 2.6 s | 12.9 s | 47.0 s | 1 | 5,067-5,908 |
| C | 270 | 2.7 s | 5.4 s | 31.6 s | 1 | 5,067-5,651 |
| D | 273 | 2.4 s | 6.2 s | 34.0 s | 1 | 5,067-5,930 |

- The p95 is taken over successful calls (31.5 s in the README is the same run, computed per line in `summary10.py`).
- The requests were the same size in every run. Run P sent about 5,000-6,000 input tokens per call and almost no thinking: thinking LOW used 572 tokens over 249 calls.
- Slow calls were not long answers. Some calls that returned only 4 output tokens took over 50 s.
- The slow calls are spread over all four products and the whole run, not one burst.
- Our app recorded a failed call as `client_timeout` (its own 60 s deadline), not by Gemini's error code. So the stored results alone cannot show the 504s. The service record below does.

## What Gemini's service record shows

`gemini_monitoring_1014.json` holds the Cloud Monitoring metrics `aiplatform.googleapis.com/publisher/online_serving/model_invocation_count` and `model_invocation_latencies`. They are hourly, for the project the set 10 runs used on 10/14 (UTC). The run P result files are dated 10/14 (UTC); the files do not record the hour.

| Hour (UTC, 10/14) | 3.8 Flash calls | 504 errors | 3.8 Flash server p50 | Flash-Lite 504 errors | Flash-Lite server p50 |
|---|---|---|---|---|---|
| 06:00-13:00 (6 hours) | 30 to 2,500 an hour | 0.1-1.1% | 5.8-20.8 s | 0-0.1% | 1.9-8.0 s |
| 14:00 | 975 | 65 (6.7%) | 43.0 s | 0 | 1.9 s |
| 15:00 | 999 | 97 (9.7%) | 185.1 s | 0 | 2.0 s |
| 16:00 | 962 | 18 (1.9%) | 20.8 s | 0 | 4.0 s |
| 17:00 | 547 | 9 (1.6%) | 24.9 s | 0 | 2.2 s |

- At 14:00-15:00 UTC, the share of 504 errors from Gemini 3.8 Flash rose 6-9 times over the earlier hours. Its server-side median latency rose from 6-21 s to 43-185 s.
- In the same hours, Gemini 3.5 Flash-Lite (the compliance and context judges) had no 504 errors and a 2 s median. The compliance judge's p95 in run P was 2.9 s. So the network and our app were fine; the slowness was in the 3.8 Flash service.
- The counts cover every 3.8 Flash call the project made in that hour, not only set 10. Other evaluations and long document reads ran at the same time, so the server medians are higher than a fact check alone would see.

## What we do about it

- A late fact alert still shows; it is not dropped.
- On a normal day the same fact checker gave p95 4.5 s over 36 calls (`eval/show_1016`).
- Planned: Provisioned Throughput (reserved capacity under an SLA), so busy shared capacity does not slow the judges.
