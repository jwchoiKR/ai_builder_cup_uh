# Sealed set 10: results per product

This file backs the numbers in the README. The raw data is in [sealed-set-10-results.json](sealed-set-10-results.json): totals and one row per product for each run, and one row per host line for the run on the current setting (line ids and outcomes only).

On 10/17 we published the set itself in [eval/sealed_set_10](../../eval/sealed_set_10/README.md): the product documents, host lines, labels, raw results and the script that rebuilds the JSON. It is no longer an unseen set.

## Setup

- 4 invented products (two skincare, one food supplement, one haircare) for the Singapore market, with their own documents. The app had never seen them (set made 10/14).
- 180 host lines, half in English and half in Korean. GPT wrote them with a first label; a separate Claude critic labelled the same lines blind.
- A Windows TTS voice speaks each line into the real Chirp 3 speech-to-text path, so speech-to-text errors count.
- Scored: 162 natural lines (54 with a violation: 26 regulation, 28 product fact; 108 safe).
- Left out and marked in the JSON:
  - 12 stress lines where we cut one sentence into two audio clips on purpose. A host does not speak like that; they are reported apart below.
  - 6 lines that need a fact not on the prompter or a rule not in the product's regulation document (user ruling 10/14).
- Each run waited up to 60 s for the compliance judge and the fact checker. From D-468 the app does the same: a slow answer still shows, late.

## Totals

| Run | Detection | False alerts | Red alert on a non-regulation line | Compliance call p50 / p95 | Fact call p50 / p95 |
|---|---|---|---|---|---|
| **P · current setting** (compliance Flash-Lite LOW), 10/15 night | **96.3%** (52 of 54) | **0%** (0 of 108) | 0 | 1.4 / 2.9 s | 6.0 / 31.5 s |
| B · compliance Flash-Lite MEDIUM, 10/14 | 100% (54 of 54) | 0.9% (1 of 108) | 0 | 2.7 / 4.7 s | 2.6 / 12.9 s |
| C · compliance Flash-Lite HIGH, 10/14 | 100% (54 of 54) | 0% (0 of 108) | 0 | 3.4 / 5.9 s | 2.7 / 5.3 s |
| D · compliance Gemini 3.8 Flash LOW, 10/14 | 100% (54 of 54) | 0.9% (1 of 108) | 0 | 2.7 / 6.4 s | 2.4 / 5.6 s |

- The fact checker is Gemini 3.8 Flash LOW in every run.
- Call times are one call, from input to output. Retries are not included, and failed calls are counted apart (P: 29 client timeouts, B and C: 2, D: 4).
- During run P, Gemini 3.8 Flash returned 504 errors: Google's service record shows 6.7% and 9.7% of its calls in the two busiest hours (0.1-1.1% in the hours before), and its server median latency rose to 43-185 s. Flash-Lite had no 504 errors in the same hours, and our requests were the same size as in the other runs. Both missed lines are fact checks that never came back. Our app logged these calls as client timeouts (its own 60 s deadline), so the 504s come from Cloud Monitoring, not from the result files: [eval/sealed_set_10/latency_run_p.md](../../eval/sealed_set_10/latency_run_p.md).
- The one false alert in B and D is the same line: the host gave the regular price, and the fact checker compared it with the live price.

## Rerun on 10/17 with the current build

Same lines and run P's settings, on main 826ae40 (the deployed code), in project ai-budiler-cup-uh-team-pjt. X2 and X4 (Korean documents) were read for an English host, the only host language the app now supports, so their prompter points are in English.

| | Run P (10/14) | Rerun (10/17) |
|---|---|---|
| Detection | 96.3% (52 of 54) | 94.4% (51 of 54) |
| False alerts | 0 of 108 | 1 of 108 |
| Fact checker p50 / p95 (one call, successful calls) | 6.0 / 31.5 s | 2.3 / 7.0 s |
| Compliance judge p95 | 2.9 s | 2.8 s |
| Alerts within 5 s / 10 s | 34 / 45 of 54 | 47 / 51 of 54 |
| Failed calls (counted apart) | 29 client timeouts | 4 client timeouts, one 429 |

- Missed: X2-14 and X3-37 are fact checks Gemini did not answer within 60 s (Cloud Monitoring shows 12 Gemini 3.8 Flash 504s and 55 429s among about 1,000 calls in that half hour); X3-31 is a model miss.
- False alert: X4-38, a line in Korean that names the bundle's regular price.
- Files: `eval/sealed_set_10/results/rerun_1017/`; `python eval/sealed_set_10/summary_rerun_1017.py out.json` rebuilds these numbers.

## How fast the host sees an alert

Detected lines by the time from the end of the line to the alert on the host screen:

| Run | Within 5 s | Within 10 s | Within 20 s | At all |
|---|---|---|---|---|
| P (during Gemini 3.8 Flash 504 errors) | 34 | 45 | 50 | 52 |
| B | 50 | 53 | 54 | 54 |
| C | 34 | 54 | 54 | 54 |
| D | 45 | 52 | 53 | 54 |

The 5 s pass line is not met. Most late alerts are fact checks on Gemini 3.8 Flash.

## Per product, run P

| Product | Detection | False alerts | Compliance call p95 | Fact call p95 |
|---|---|---|---|---|
| 1 Skincare | 100% (14 of 14) | 0 of 27 | 2.3 s | 17.0 s |
| 2 Skincare | 92.3% (12 of 13) | 0 of 27 | 2.7 s | 44.7 s |
| 3 Food supplement | 92.3% (12 of 13) | 0 of 27 | 3.3 s | 24.4 s |
| 4 Haircare | 100% (14 of 14) | 0 of 27 | 2.3 s | 31.5 s |

Per product in run P, 2 of 4 products meet the 95% detection line and all 4 meet the false-alert line. In runs B, C and D every product detects all of its violations.

## Stress lines (reported apart)

The 12 cut sentences are all safe lines. In each run, 4 of them got a false alert: the first clip alone reads as a complete wrong price or caution (made-up example: "it's fifty" + "four dollars"). The 2 s alert wait we tried for this (D-462 to D-465) only hid one of them, so it was turned off again (D-467).

## Earlier sets

Set 7 (10/8, 6 products) gave 95.5% detection and 1.6% false alerts. It ran under older conditions: the fact checker read the whole product documents instead of the prompter, the live judges dropped answers after 5 s, and alert times included retries. Its numbers are not comparable with these.
