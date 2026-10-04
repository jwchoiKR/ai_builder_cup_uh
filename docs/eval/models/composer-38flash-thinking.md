# Composer thinking level: LOW vs MEDIUM · 2026-10-05

Model `gemini-3.8-flash` on Vertex AI (`global`), prompt `answer_composer_v1`, `COMPOSER_THINKING` = LOW vs MEDIUM (D-067). Script: `backend/scripts/eval_composer.py`.

## Setup
- **Questions:** 26 distinct composer inputs (product, intent, slots, canonical question, promo), covering 49 comments:
  - every product question of bursts B1–B4 (scenes S03, S04, S09, S11);
  - every comment eval case whose recorded triage is a composable question.
- **How each question was built:**
  - triage output from the recorded fixtures (`tests/fixtures/llm/comment_triage/`, scenario = scene or case id);
  - product from `attribute_product`: context product = cream for B1–B4, the case's `current_product_id` for eval cases;
  - only `is_composable` questions kept; B4 questions run with `promo_time_sale_10` active.
- **Runs:** 3 per question and mode, modes interleaved, concurrency 4.
- **Deadline:** 30 s, so latency is measured in full. The production deadline (`COMPOSER_TIMEOUT_MS` = 12000 ms) is reported separately.
- **Passages and checks:** same as the pipeline: `gather_passages` with BM25 and prefetch, plus the promo passage; `verify_answer` (§8.9.4).
- **Rates:** over all runs, so a non-ok call counts as not verified and not grounded. Latency is over ok calls.

## Aggregate
| Mode | verify_answer pass | grounded | needs_human | statuses | p50 | p95 | max | ≤ 12 s | ≤ 15 s | thinking tokens (mean) |
|---|---|---|---|---|---|---|---|---|---|---|
| LOW | 58/78 (74%) | 60/78 (77%) | 21/78 (27%) | ok 78 | 2.5 s | 10.5 s | 22.6 s | 75/78 (96%) | 77/78 (99%) | 0 |
| MEDIUM | 56/78 (72%) | 60/78 (77%) | 27/78 (35%) | ok 78 | 5.9 s | 12.0 s | 19.5 s | 73/78 (94%) | 76/78 (97%) | 690 |

## Conclusion
- Deadline (12 s, `COMPOSER_TIMEOUT_MS`): LOW finished 75/78 (96%) of calls in time, MEDIUM 73/78 (94%). Latency p50/p95: LOW 2.5 s / 10.5 s, MEDIUM 5.9 s / 12.0 s.
- First-answer target (≤ 15 s, §3.7): LOW 77/78 (99%), MEDIUM 76/78 (97%) of calls.
- Quality: verify_answer pass rate LOW 74% vs MEDIUM 72%; grounded LOW 77% vs MEDIUM 77%; needs_human LOW 27% vs MEDIUM 35%. Mean thinking tokens LOW 0, MEDIUM 690.

## Per question
| # | Canonical question | Product | Intent | Promo | LOW pass | MEDIUM pass | LOW p50 | MEDIUM p50 | Typical verify errors | Covers |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | How much is it? | cream_hydra_barrier | price | — | 2/3 | 3/3 | 2.2 s | 8.5 s | LOW: number 48 is not the value of 'set' in the cited quotes ×1 | B1/S03 Lee: How much is the cream?; B1/S03 Kumar: price?; B1/S03 Nur: how much is it; +4 more |
| 2 | How much is the set? | ampoule_deep_hydration | set_price | — | 3/3 | 3/3 | 2.2 s | 9.0 s | — | B1/S03 Jia Hui: how much is the set with the ampoule? |
| 3 | Is it suitable for oily skin? | cream_hydra_barrier | skin_type_suitability | — | 3/3 | 2/3 | 2.9 s | 5.5 s | MEDIUM: more than 2 sentences ×1 | B2/S04 Raj: Is it OK for oily skin?; B2/S04 Priya: my skin is super oily, will this work for me?; B2/S04 Hafiz: good for oily skin or not; +7 more |
| 4 | Can it be used under makeup? | cream_hydra_barrier | makeup_compatibility | — | 3/3 | 3/3 | 2.5 s | 11.6 s | — | B2/S04 Ming: Can I use it under makeup?; B2/S04 Farah: does it pill under foundation?; B2/S04 Aisha: can i put makeup on after this; +2 more |
| 5 | Is it suitable for dry skin? | cream_hydra_barrier | skin_type_suitability | — | 3/3 | 3/3 | 2.8 s | 6.1 s | — | B2/S04 Kai: is it okay for dry skin too?; C07: is it ok for dry skin |
| 6 | Does it contain fragrance? | cream_hydra_barrier | fragrance | — | 3/3 | 3/3 | 2.2 s | 4.8 s | — | B2/S04 Hannah: Does it have fragrance? |
| 7 | Can it be used during pregnancy? | cream_hydra_barrier | pregnancy_breastfeeding | — | 3/3 | 3/3 | 3.0 s | 8.9 s | — | B3/S09 Jun: Can I use it while pregnant?; B3/S09 Nadia: is this safe during pregnancy??; B3/S09 Wei Ling: I'm pregnant, can I use the cream? |
| 8 | Can it be used for eczema? | cream_hydra_barrier | medical_condition | — | 0/3 | 0/3 | 2.0 s | 5.4 s | LOW: not grounded ×3; LOW: empty answer ×3 | B3/S09 Tom: my daughter has eczema can she use this |
| 9 | How much is it? | cream_hydra_barrier | price | promo_time_sale_10 | 3/3 | 3/3 | 2.1 s | 6.9 s | — | B4/S11 Lee: how much is the cream now?; B4/S11 Daniel: price now? |
| 10 | What is the bundle or set price? | cream_hydra_barrier | set_price | promo_time_sale_10 | 2/3 | 0/3 | 2.6 s | 8.2 s | MEDIUM: number 55.8 is not the value of 'set' in the cited quotes ×3; LOW: number 55.8 is not the value of 'set' in the cited quotes ×1 | B4/S11 Priya: what's the set price with the time sale? |
| 11 | How much is the set? | cream_hydra_barrier | set_price | — | 3/3 | 3/3 | 2.5 s | 5.8 s | — | C05: how much is the set? |
| 12 | Can I use it while pregnant? | cream_hydra_barrier | pregnancy_breastfeeding | — | 3/3 | 3/3 | 2.6 s | 4.3 s | — | C09: Can I use it while pregnant? |
| 13 | Is it safe to use while breastfeeding? | ampoule_deep_hydration | pregnancy_breastfeeding | — | 3/3 | 3/3 | 2.8 s | 4.0 s | — | C10: I'm breastfeeding, is the ampoule ok? |
| 14 | Can it be used by children with eczema? | cream_hydra_barrier | medical_condition | — | 0/3 | 0/3 | 2.0 s | 4.5 s | LOW: not grounded ×3; LOW: empty answer ×3 | C11: my son has eczema, can he use it |
| 15 | Will it reduce wrinkles? | cream_hydra_barrier | efficacy_claim | — | 0/3 | 0/3 | 2.0 s | 7.9 s | LOW: not grounded ×3; LOW: empty answer ×3 | C12: will it get rid of my wrinkles? |
| 16 | Does it sting or tingle on the skin? | ampoule_deep_hydration | allergy_sensitivity | — | 3/3 | 3/3 | 3.4 s | 8.5 s | — | C13: Does the ampoule sting? |
| 17 | Can I use it with vitamin C? | ampoule_deep_hydration | how_to_use | — | 3/3 | 3/3 | 2.4 s | 5.4 s | — | C14: can I use it with vitamin C? |
| 18 | What is the volume or size? | cream_hydra_barrier | volume | — | 3/3 | 3/3 | 2.3 s | 4.3 s | — | C23: how many ml? |
| 19 | What is the concentration of niacinamide in it? | ampoule_deep_hydration | ingredient_amount | — | 3/3 | 3/3 | 3.9 s | 5.0 s | — | C24: how much niacinamide is in it |
| 20 | Is it fragrance-free? | cream_hydra_barrier | fragrance | — | 3/3 | 3/3 | 2.4 s | 6.6 s | — | C25: is it fragrance free |
| 21 | Which product should I use first, the cream or the ampoule? | cream_hydra_barrier | routine_order | — | 3/3 | 3/3 | 2.2 s | 9.6 s | — | C26: which one should I buy first, cream or ampoule? |
| 22 | Is it suitable for teenagers? | cream_hydra_barrier | age_suitability | — | 0/3 | 0/3 | 2.8 s | 8.6 s | LOW: not grounded ×3; LOW: empty answer ×3 | C27: is it suitable for teens? |
| 23 | Where is it manufactured? | cream_hydra_barrier | origin | — | 3/3 | 3/3 | 1.9 s | 3.4 s | — | C28: where is it made |
| 24 | How long does a bottle last? | ampoule_deep_hydration | volume | — | 0/3 | 0/3 | 1.9 s | 11.2 s | LOW: not grounded ×3; LOW: empty answer ×3 | C33: how long will a bottle last? |
| 25 | Is it tested on animals? | cream_hydra_barrier | origin | — | 0/3 | 0/3 | 2.7 s | 3.9 s | LOW: not grounded ×3; LOW: empty answer ×3 | C34: is it tested on animals? |
| 26 | Can I use it under makeup? | cream_hydra_barrier | makeup_compatibility | — | 3/3 | 3/3 | 2.6 s | 6.0 s | — | C35: does it pill under foundation? |
