# Spoken-answer auto-post (D-110)

2026-10-05 · 40 cases × 3 runs · production agents (split3) + `logic.publish.decide`. Cases: `data/eval/verbal_post_cases.jsonl`.

- **False posts: 0** (target 0)
- Missed posts: 11 of 66 expected posts (allowed; the card stays and "Confirm and post" still works)

| category | runs | posted | false posts | missed posts |
|---|---|---|---|---|
| added_caveat | 6 | 0 | 0 | 0 |
| answer_only_shown | 30 | 24 | 0 | 6 |
| answer_only_waiting | 18 | 16 | 0 | 2 |
| contradiction | 6 | 0 | 0 | 0 |
| hedge | 6 | 0 | 0 | 0 |
| hypothetical | 3 | 0 | 0 | 0 |
| match | 18 | 15 | 0 | 3 |
| other_group | 3 | 0 | 0 | 0 |
| question_back | 6 | 0 | 0 | 0 |
| quote | 3 | 0 | 0 | 0 |
| readout | 6 | 0 | 0 | 0 |
| retracted | 6 | 0 | 0 | 0 |
| wrong_number | 9 | 0 | 0 | 0 |

## False posts

- none

## Missed posts

- HV06 run 0 (answer_only_shown): verbal_not_posted g_allantoin · a number differs from the verified draft
- HV13 run 0 (answer_only_shown): verbal_not_posted g_amp_ph · a number differs from the verified draft
- HV16 run 0 (answer_only_waiting): none g_panthenol · compliance alert or contradicted fact
- HV22 run 0 (match): verbal_not_posted g_ph · a number differs from the verified draft
- HV06 run 1 (answer_only_shown): verbal_not_posted g_allantoin · a number differs from the verified draft
- HV13 run 1 (answer_only_shown): verbal_not_posted g_amp_ph · a number differs from the verified draft
- HV16 run 1 (answer_only_waiting): none g_panthenol · compliance alert or contradicted fact
- HV22 run 1 (match): verbal_not_posted g_ph · a number differs from the verified draft
- HV06 run 2 (answer_only_shown): verbal_not_posted g_allantoin · a number differs from the verified draft
- HV13 run 2 (answer_only_shown): verbal_not_posted g_amp_ph · a number differs from the verified draft
- HV22 run 2 (match): verbal_not_posted g_ph · a number differs from the verified draft
