# Sealed set 7: results per product

This file backs the numbers in the README. The raw data is in [sealed-set-7-results.json](sealed-set-7-results.json): totals, one row per product, and one row per host line with its outcome.

The set itself stays sealed. The JSON has line ids, product numbers and outcomes, but no host lines, labels or product documents. We hold the set back so that the next version of the app is again tested on products it has never seen.

## Setup

- 6 invented products, each with its own documents in two languages. The app had never seen them (set made 10/8).
- 48 host lines per product, 288 in all. GPT wrote them with a first label; a separate Claude critic labelled the same lines blind.
- A Windows TTS voice speaks each line into the real Chirp 3 speech-to-text path, so speech-to-text errors count.
- Scored: 261 lines (134 with a violation, 127 safe). Left out and marked in the JSON: 18 lines where two hosts talk over each other, 4 stress lines, and 5 lines that need a rule outside the product's own pack.
- First run: the set was fresh. Second run: the same set after one change chosen from the first run (a line that expects an answer is judged together with the next line).
- Critic rulings after the run (marked in the JSON): 2 corrections credited, 3 extra alerts not penalised.

## Totals

| | First run | Second run | Pass line |
|---|---|---|---|
| Detection | 94.0% (126 of 134) | 95.5% (128 of 134) | ≥ 95% |
| False alerts on safe lines | 2.4% (3 of 127) | 1.6% (2 of 127) | < 1% |
| Wrong strongest alerts | 0 | 0 | 0 |
| Alert p95, end of line to host screen | 4.5 s | 4.2 s | ≤ 5 s |
| Judge calls / timeouts | 1,154 / 28 | 1,037 / 21 | |

## Per product, second run

| Product | Detection | False alerts | Alert p95 |
|---|---|---|---|
| 1 Lip balm SPF20 | **82.6%** (19 of 23) | **4.8%** (1 of 21) | 4.2 s |
| 2 Fermented toner | 100% (23 of 23) | 0% (0 of 19) | 4.2 s |
| 3 Omega-3 softgels | 100% (23 of 23) | 0% (0 of 22) | 4.3 s |
| 4 Dry shampoo | 100% (23 of 23) | **4.8%** (1 of 21) | 4.8 s |
| 5 Kids' sunscreen SPF50 | 95.7% (22 of 23) | 0% (0 of 22) | 4.4 s |
| 6 Cold brew concentrate | **94.7%** (18 of 19) | 0% (0 of 22) | 1.7 s |

Bold marks a missed pass line. 4 of 6 products meet the detection line, 4 of 6 meet the false-alert line, and all 6 meet the latency line. Both false alerts come from speech-to-text writing "four" as "for" next to a number.

## Per product, first run

| Product | Detection | False alerts | Alert p95 |
|---|---|---|---|
| 1 Lip balm SPF20 | **87.0%** (20 of 23) | **4.8%** (1 of 21) | **9.6 s** |
| 2 Fermented toner | 100% (23 of 23) | 0% (0 of 19) | 4.5 s |
| 3 Omega-3 softgels | 95.7% (22 of 23) | **4.5%** (1 of 22) | **6.4 s** |
| 4 Dry shampoo | 100% (23 of 23) | **4.8%** (1 of 21) | 4.3 s |
| 5 Kids' sunscreen SPF50 | 95.7% (22 of 23) | 0% (0 of 22) | 3.5 s |
| 6 Cold brew concentrate | **84.2%** (16 of 19) | 0% (0 of 22) | 3.9 s |

## How the numbers are computed

- Detection: a line with a violation counts when the host screen shows a matching alert for it (the right rule, or the right product fact).
- False alert: an alert on a line with no violation.
- Alert p95: the 95th percentile over every alert shown in that product's show, from the end of the spoken line to the host screen. The JSON's `first_alert_ms` is the first alert on each line.
- The judge setup is the one frozen on 10/8: Gemini 3.5 Flash-Lite, compliance MEDIUM, facts LOW, fact prompt v5, STT endpointing STANDARD. Later changes (the 10/9 simplification, the fact checker on Gemini 3.8 Flash from 10/15) have not been run on this set.
