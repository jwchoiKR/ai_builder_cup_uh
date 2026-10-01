# Composer verify failures · 2026-10-01

**Question:** which composer answers fail `verify_answer` (§8.9.4), and which rule rejects them? Two kinds of failure are kept apart:
- **(a) The sheet has no answer (expected).** The model returns an empty, ungrounded answer and the group goes to the operator as "Needs review".
- **(b) The answer was correct but verify rejected it.** These would be fixed in `verify_answer` or the composer.

## Sources
- **Composer eval, run C:** `scripts/eval_composer.py --calls ../docs/eval/composer-calls.json`.
  - 25 composer inputs × 3 runs × 2 thinking levels = 150 calls on Vertex AI (`gemini-3.8-flash`).
  - `docs/eval/composer-calls.json` holds every call: answer, citations, verify errors and passage ids.
- **Earlier runs:** run A and run B of `docs/eval/composer-thinking.md`.
- **Full demo runs on Vertex:** `scripts/record_demo_fixtures.py`. The rejected composer answers of both runs are listed below.

## Composer eval: every failed call (run C)
LOW is the production setting (`COMPOSER_THINKING`, D-067).

| # | Question (product, intent) | LOW | MEDIUM | Failing rules (every failed call) | What the sheet says | Kind |
|---|---|---|---|---|---|---|
| 8 | Can it be used by children with eczema? (cream, `medical_condition`) | 0/3 | 0/3 | rule 1 `not grounded` + `empty answer`; rule 2 `no citation` | Nothing on children or eczema-affected skin. "Treats eczema, dermatitis…" is a **not-approved claim**; "Keep out of reach of children" is a storage caution. | (a) |
| 14 | Will it reduce wrinkles? (cream, `efficacy_claim`) | 0/3 | 0/3 | same three errors | "Removes wrinkles or reverses skin ageing" is a **not-approved claim**; no approved claim is about wrinkles. | (a) |
| 21 | Is it suitable for teenagers? (cream, `age_suitability`) | 0/3 | 0/3 | same three errors | No age statement. The in-house test had participants aged 20–49; "all users" in the men FAQ does not say anything about age. | (a) |
| 23 | How long does a bottle last? (ampoule, `volume`) | 0/3 | 0/3 | same three errors | Volume 30 mL; no amount per use, so no duration. "Use within 12 months after opening" is shelf life, not how long a bottle lasts. | (a) |
| 24 | Is it tested on animals? (cream, `origin`) | 0/3 | 0/3 | same three errors | Not mentioned anywhere in the sheet. | (a) |
| 15 | Does it sting or tingle on the skin? (ampoule, `allergy_sensitivity`) | 3/3 | 2/3 | MEDIUM: `timeout` after 30 s (no output) | Answered and verified in the other 5 calls. | not a verify failure (latency, MEDIUM only) |

**In every failed call the model itself declined:** `grounded=false`, empty answer, no citations. Rules 1 and 2 then reject it, as designed.
- **Rules that rejected nothing:**
  - rule 1: length and sentence count;
  - rule 2: unknown passage, quote not found;
  - rule 3: wrong product;
  - rule 4: number not quoted;
  - rule 5: restricted phrase, not-approved claim.
- The 20 other questions passed 3/3 at LOW.

**Earlier runs:**
- **Run B:** the same five questions failed with the same three errors; the other failures were timeouts.
- **Run A (before D-068):** two more questions failed the same way. "Does it sting?" and "Where is it manufactured?" returned an empty answer, because BM25 had not retrieved the Cautions or "Made in" passage.
  - The sheet had the answer, so these were **retrieval misses, not verify rejections**.
  - D-068 fixed them; both now pass.

## Full demo run (Vertex AI)
`scripts/record_demo_fixtures.py` plays `data/demo/host_script.md` S02–S14 with bursts B1–B5 and the time sale. Two runs were made on 2026-10-01.

**Run 2: clean (kept as the recording-day backup, D-086).** 85 agent calls, all `ok`, including 15 composer calls.
- 14 composer answers passed `verify_answer`.
- **1 was rejected:**

  | Scene | Question | Failing rules | Kind |
  |---|---|---|---|
  | S09 (B3) | "Can it be used by children with eczema?" (cream, `medical_condition`) | rule 1 `not grounded` + `empty answer`; rule 2 `no citation` | (a), same as eval #8 |

- "Do you ship to Malaysia?" (`shipping`, product scope none) is routed to the operator before the composer, so it is not a verify result.

**Run 1: not clean (discarded).** The same eczema rejection (a). The composer call for "Does the ampoule sting?" (S12, B5) hit the 12 s production deadline. That is a timeout, not a verify rejection. The call left no fixture, so the run was repeated.

## Result
- **Kind (b), "the answer was correct but verify rejected it": none.** This covers 150 eval calls and the composer calls of both demo runs (15 in the clean run). Every rejection was the model's own empty, ungrounded answer for a question the sheet does not answer.
  - Every answer that cited the sheet passed all five rules.
  - No quote, number, product, length, sentence-count, restricted-phrase or not-approved-claim check fired on an answer.
- **So `verify_answer` and the composer are unchanged.** There was nothing of kind (b) to fix (D-087).
  - Kind (a) works as designed: these groups go to the operator as "Needs review" without a draft.
  - The two former misses ("Does it sting?", "Where is it manufactured?") were retrieval misses, already fixed by D-068.
- **Rule 5 note:** rule 5 (restricted wording, even negated, §8.9.4) is strict by spec. It rejected nothing in these runs, so its strictness cost nothing here.
