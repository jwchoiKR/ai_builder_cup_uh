# Spoken-answer auto-post (D-110)

2026-10-05 · 48 cases × 3 runs · production agents (split3) + `logic.publish.decide`. Cases: `data/eval/verbal_post_cases.jsonl`.

- **False posts: 1** (target 0)
- Missed posts: 7 of 78 expected posts (allowed; the card stays and "Confirm and post" still works)

| category | runs | posted | false posts | missed posts |
|---|---|---|---|---|
| added_caveat | 6 | 0 | 0 | 0 |
| answer_only_shown | 6 | 6 | 1 | 1 |
| answer_only_waiting | 12 | 7 | 0 | 5 |
| contradiction | 15 | 0 | 0 | 0 |
| hedge | 6 | 0 | 0 | 0 |
| hypothetical | 3 | 0 | 0 | 0 |
| match | 60 | 59 | 0 | 1 |
| other_group | 3 | 0 | 0 | 0 |
| question_back | 6 | 0 | 0 | 0 |
| quote | 3 | 0 | 0 | 0 |
| readout | 3 | 0 | 0 | 0 |
| retracted | 3 | 0 | 0 | 0 |
| wrong_number | 18 | 0 | 0 | 0 |

## False posts

- V46 run 0 (answer_only_shown): post g_ampsize · 

## Missed posts

- V44 run 0 (answer_only_waiting): none  · not an answer to an offered question
- V46 run 0 (answer_only_shown): post g_ampsize · 
- V42 run 1 (answer_only_waiting): none  · not an answer to an offered question
- V44 run 1 (answer_only_waiting): none  · not an answer to an offered question
- V18 run 2 (match): none  · not an answer to an offered question
- V42 run 2 (answer_only_waiting): none  · not an answer to an offered question
- V44 run 2 (answer_only_waiting): none  · not an answer to an offered question
