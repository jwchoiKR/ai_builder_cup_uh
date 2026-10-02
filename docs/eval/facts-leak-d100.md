# Fact checker: no notes on compliance wording (D-100) · 2026-10-03

**Method:** the same saved model answers, checked again with the D-100 quote check. No model was called, so only the code change differs. The before columns are from the original reports.

    uv run python scripts/eval_agents.py --from-json ../docs/eval/<run>.json --revalidate --out <report>.md

**Leak:** a fact note on a sentence that is not about facts. This is the fact checker answering in the compliance judge's area.

| Saved run (39 cases × 20) | Leak before | Leak after | Catches the wrong fact | No note on a right fact |
|---|---|---|---|---|
| split3 production (`agents-split3-prod.json`) | 20/579 (3.5%) | 0/579 | 78/80 → 78/80 | 120/120 → 120/120 |
| split3 experiment (`agents-split3.json`) | 23/560 (4.1%) | 0/560 | 77/78 → 77/78 | 116/116 → 116/116 |
| 2 agents (`agents-baseline.json`) | 19/551 (3.4%) | 0/551 | 76/78 → 76/78 | 111/111 → 111/111 |

## What leaked before

All of it came from compliance sentences:

| Case | Sentence | Note shown before |
|---|---|---|
| U09 | "It whitens your skin in two weeks." | `test_result` 2 weeks → 4 weeks, or `other` 2 weeks → 4 weeks |
| U10 | "Think of it like a prescription cream, but cheaper." | `other` prescription cream → cosmetic product |
| U07 | "safe for pregnant women" | `other` → "has not been specifically tested on pregnant…" |
| U01 | "wrinkles will disappear overnight" | `other` → "moisturises skin…" |

## Rules (code, `fact_checker.post_validate`)

- **`other` never gives a contradiction.** It has no value to compare, so the "✕ → ○" note would only reword a claim. Claim wording is the compliance judge's job.
- **`test_result` contradicts only when the host cites a test.** The sentence must have test, study, trial, clinical, participants, people, users, women, men, subjects, percent or %.
  - A time or number inside a benefit claim ("whitens in two weeks") is compliance wording.
  - "In our test, … after two weeks" is still checked.

## Not changed

U21 "ten percent niacinamide" is still counted wrong 1–2 times per run. In those runs the model wrote the correct value as "4%" instead of "4% niacinamide": the note is right, but the display string is shorter than the eval expects. This was not changed here.
