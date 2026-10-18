# Test set 10 (published 10/17)

This is the test set behind the README numbers: detection 96.3% (52 of 54), false alerts 0% (0 of 108), no red alert on a line without a regulation problem. It was sealed while we built the app: the app and its developer never saw it before the runs. We publish it now so anyone can check the numbers. From here on it is no longer an unseen set.

## What is in it

| Path | What |
|---|---|
| `products/product_X1.pdf` … `product_X4.pdf` | 4 invented products for the Singapore market (two skincare, one food supplement, one haircare), written as normal product documents |
| `regulations/` | the two public regulation documents the shows used: the ASEAN cosmetic claims guideline (Appendix III, 2007) and the HSA health supplements guidelines |
| `lines/live_X*.jsonl` | 180 host lines (45 per product, half English, half Korean) with their labels: risky or safe, and the kind of problem (regulation or product fact) |
| `onboarding10_stt/live_X*.jsonl` | the same lines as the scorer reads them, after a TTS voice spoke them into the real Chirp 3 speech-to-text path |
| `labels/` | `corpus.json` (the product facts the documents were written from), `truth_gpt.json` (GPT's first labels), `labels_sonnet.jsonl` (a separate Claude critic's blind labels of the same lines) |
| `results/pool10/` | one file per run and product: every line, the alerts the app showed, each AI call's time and status. Runs: P (the deployed setting, late on 10/14 UTC, the night of 10/14-15 KST), B, C, D (other compliance settings, earlier on 10/14) |
| `summary10.py` | builds `docs/eval/sealed-set-10-results.json` from the files above |
| `results/rerun_1017/`, `summary_rerun_1017.py` | rerun of 10/17 with the current build and run P's settings: every line and call, the product reads, and the summary (`python summary_rerun_1017.py out.json`) |
| `latency_run_p.md`, `fact_latency.py`, `gemini_monitoring_1014.json` | why run P's fact checker was slow: the stored call times and token counts, and Gemini's hourly service record (504 errors, server latency) for that night |
| `score10.py` | the per-run score we used during the runs, all lines included |

## Check the numbers

```sh
cd eval/sealed_set_10
python summary10.py check.json
```

`check.json` is identical to `docs/eval/sealed-set-10-results.json`. Run P gives 52 of 54 detected and 0 of 108 false alerts. No API key or network is needed: the script only reads the stored results.

## Scoring rules

- A risky line counts as detected when an alert of its labelled kind appears. A false alert is any alert on a safe line.
- 12 stress lines are reported apart: we cut one sentence into two audio clips on purpose, which a host does not do.
- 6 lines are out of scope and excluded (user rulings on 10/14): X1-31, X4-37 and X2-31, X2-37 need a fact that is not on the prompter (the fact checker reads only the prompter); X3-23 and X3-40 cite a rule that is not in the uploaded HSA document.
- A judge's time is one call, from input to output. Retries are not included, and failed calls are counted apart.

## Limits

- 4 products and 54 violations: one line moves detection by about 2 points.
- The lines were spoken by a Windows TTS voice.
- GPT wrote the lines and their first labels; a separate Claude critic labelled them blind, and the differences were settled by the rules above.
