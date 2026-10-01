# Composer thinking level: LOW vs MEDIUM · 2026-10-01

Model `gemini-3.8-flash` on Vertex AI (`global`), prompt `answer_composer_v1`, `COMPOSER_THINKING` = LOW vs MEDIUM (D-067). Script: `backend/scripts/eval_composer.py`.

## Setup
- **Questions:** 25 distinct composer inputs (product, intent, slots, canonical question, promo), covering 49 comments:
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

## Run history (both runs, same questions and method)

### Run A: before D-068
`gather_passages` added Key facts only for price/set_price/promo/volume. Vertex was otherwise idle.

| Mode | verify_answer pass | grounded | needs_human | statuses | p50 | p95 | max | ≤ 12 s | ≤ 15 s | thinking tokens (mean) |
|---|---|---|---|---|---|---|---|---|---|---|
| LOW | 54/75 (72%) | 54/75 (72%) | 21/75 (28%) | ok 75 | 2.0 s | 3.0 s | 7.9 s | 75/75 (100%) | 75/75 (100%) | 3 |
| MEDIUM | 53/75 (71%) | 53/75 (71%) | 26/75 (35%) | ok 74, timeout 1 | 5.3 s | 10.3 s | 14.8 s | 73/75 (97%) | 74/75 (99%) | 625 |

### Run B: after D-068
Fixed sections were added for origin, packaging, shelf life, texture, fragrance and ingredients (Key facts, Key ingredients), and Cautions for the sensitive intents.

- **Load:** run B overlapped the real-model voice rehearsals and the E2E run on the same project, and one model warm-up timed out.
- **Effect:** the latency tails and the 30 s timeouts in run B reflect that shared load, not the thinking level.
- **Detail:** the aggregate and per-question tables below are from run B.

### Conclusion
- **Quality:** equal within noise in both runs. D-068 raised verification for both levels:
  - "Does it sting?" now passes 3/3 in both modes;
  - "Where is it manufactured?" passes 3/3 on MEDIUM and 2/3 on LOW (LOW's one miss was a timeout, not a wrong answer).
- **Speed:** LOW is about 2.5× faster at the median in both runs, and in the unloaded run every call finished within the 12 s deadline.
- **Setting:** `COMPOSER_THINKING=LOW` stays.

## Aggregate (run B)
| Mode | verify_answer pass | grounded | needs_human | statuses | p50 | p95 | max | ≤ 12 s | ≤ 15 s | thinking tokens (mean) |
|---|---|---|---|---|---|---|---|---|---|---|
| LOW | 58/75 (77%) | 58/75 (77%) | 16/75 (21%) | ok 72, timeout 3 | 2.2 s | 4.9 s | 23.2 s | 69/75 (92%) | 70/75 (93%) | 0 |
| MEDIUM | 60/75 (80%) | 60/75 (80%) | 20/75 (27%) | ok 74, timeout 1 | 5.5 s | 12.7 s | 26.2 s | 68/75 (91%) | 72/75 (96%) | 684 |

## Conclusion
- Deadline (12 s, `COMPOSER_TIMEOUT_MS`): LOW finished 69/75 (92%) of calls in time, MEDIUM 68/75 (91%). Latency p50/p95: LOW 2.2 s / 4.9 s, MEDIUM 5.5 s / 12.7 s.
- First-answer target (≤ 15 s, §3.7): LOW 70/75 (93%), MEDIUM 72/75 (96%) of calls.
- Quality: verify_answer pass rate LOW 77% vs MEDIUM 80%; grounded LOW 77% vs MEDIUM 80%; needs_human LOW 21% vs MEDIUM 27%. Mean thinking tokens LOW 0, MEDIUM 684.

## Per question
| # | Canonical question | Product | Intent | Promo | LOW pass | MEDIUM pass | LOW p50 | MEDIUM p50 | Typical verify errors | Covers |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | How much is it? | cream_hydra_barrier | price | — | 3/3 | 3/3 | 2.7 s | 7.4 s | — | B1/S03 Lee: How much is the cream?; B1/S03 Kumar: price?; B1/S03 Nur: how much is it; +4 more |
| 2 | How much is the bundle set? | ampoule_deep_hydration | set_price | — | 3/3 | 3/3 | 2.2 s | 7.5 s | — | B1/S03 Jia Hui: how much is the set with the ampoule? |
| 3 | Is it suitable for oily skin? | cream_hydra_barrier | skin_type_suitability | — | 3/3 | 3/3 | 2.2 s | 5.1 s | — | B2/S04 Raj: Is it OK for oily skin?; B2/S04 Priya: my skin is super oily, will this work for me?; B2/S04 Hafiz: good for oily skin or not; +7 more |
| 4 | Can I use it under makeup? | cream_hydra_barrier | makeup_compatibility | — | 3/3 | 3/3 | 1.8 s | 4.8 s | — | B2/S04 Ming: Can I use it under makeup?; B2/S04 Farah: does it pill under foundation?; B2/S04 Aisha: can i put makeup on after this; +1 more |
| 5 | Is it suitable for dry skin? | cream_hydra_barrier | skin_type_suitability | — | 3/3 | 3/3 | 2.6 s | 6.2 s | — | B2/S04 Kai: is it okay for dry skin too?; C07: is it ok for dry skin |
| 6 | Does it contain fragrance? | cream_hydra_barrier | fragrance | — | 3/3 | 3/3 | 2.2 s | 5.1 s | — | B2/S04 Hannah: Does it have fragrance? |
| 7 | Can I use it while pregnant? | cream_hydra_barrier | pregnancy_breastfeeding | — | 3/3 | 3/3 | 3.0 s | 4.9 s | — | B3/S09 Jun: Can I use it while pregnant?; B3/S09 Nadia: is this safe during pregnancy??; B3/S09 Wei Ling: I'm pregnant, can I use the cream?; +1 more |
| 8 | Can it be used by children with eczema? | cream_hydra_barrier | medical_condition | — | 0/3 | 0/3 | 2.2 s | 5.8 s | LOW: not grounded ×3; LOW: empty answer ×3 | B3/S09 Tom: my daughter has eczema can she use this; C11: my son has eczema, can he use it |
| 9 | How much is it? | cream_hydra_barrier | price | promo_time_sale_10 | 3/3 | 3/3 | 2.1 s | 5.1 s | — | B4/S11 Lee: how much is the cream now?; B4/S11 Daniel: price now? |
| 10 | What is the bundle or set price? | cream_hydra_barrier | set_price | promo_time_sale_10 | 3/3 | 3/3 | 2.8 s | 9.5 s | — | B4/S11 Priya: what's the set price with the time sale? |
| 11 | How much is the set? | cream_hydra_barrier | set_price | — | 3/3 | 3/3 | 2.1 s | 8.1 s | — | C05: how much is the set? |
| 12 | Can it be used under makeup? | cream_hydra_barrier | makeup_compatibility | — | 3/3 | 3/3 | 2.0 s | 11.4 s | — | C08: Can I use it under makeup? |
| 13 | Is it safe to use while breastfeeding? | ampoule_deep_hydration | pregnancy_breastfeeding | — | 3/3 | 3/3 | 2.2 s | 4.4 s | — | C10: I'm breastfeeding, is the ampoule ok? |
| 14 | Will it reduce wrinkles? | cream_hydra_barrier | efficacy_claim | — | 0/3 | 0/3 | 2.1 s | 11.5 s | LOW: not grounded ×3; LOW: empty answer ×3 | C12: will it get rid of my wrinkles? |
| 15 | Does it sting or tingle on the skin? | ampoule_deep_hydration | allergy_sensitivity | — | 3/3 | 3/3 | 2.5 s | 18.2 s | — | C13: Does the ampoule sting? |
| 16 | Can I use it with vitamin C? | ampoule_deep_hydration | how_to_use | — | 3/3 | 3/3 | 2.1 s | 4.2 s | — | C14: can I use it with vitamin C? |
| 17 | What is the volume or size? | cream_hydra_barrier | volume | — | 3/3 | 3/3 | 2.4 s | 3.4 s | — | C23: how many ml? |
| 18 | What is the concentration of niacinamide in it? | ampoule_deep_hydration | ingredient_amount | — | 3/3 | 3/3 | 1.9 s | 4.4 s | — | C24: how much niacinamide is in it |
| 19 | Is it fragrance-free? | cream_hydra_barrier | fragrance | — | 3/3 | 3/3 | 2.4 s | 4.8 s | — | C25: is it fragrance free |
| 20 | Which product should I use first, the cream or the ampoule? | cream_hydra_barrier | routine_order | — | 3/3 | 3/3 | 2.6 s | 5.5 s | — | C26: which one should I buy first, cream or ampoule? |
| 21 | Is it suitable for teenagers? | cream_hydra_barrier | age_suitability | — | 0/3 | 0/3 | 2.2 s | 6.3 s | LOW: not grounded ×3; LOW: empty answer ×3 | C27: is it suitable for teens? |
| 22 | Where is it manufactured? | cream_hydra_barrier | origin | — | 2/3 | 3/3 | 1.7 s | 3.5 s | LOW: timeout: deadline 30000 ms ×1 | C28: where is it made |
| 23 | How long does a bottle last? | ampoule_deep_hydration | volume | — | 0/3 | 0/3 | 1.5 s | 6.2 s | LOW: not grounded ×2; LOW: empty answer ×2 | C33: how long will a bottle last? |
| 24 | Is it tested on animals? | cream_hydra_barrier | origin | — | 0/3 | 0/3 | 2.3 s | 2.9 s | LOW: not grounded ×3; LOW: empty answer ×3 | C34: is it tested on animals? |
| 25 | Can I use it under makeup? | cream_hydra_barrier | makeup_compatibility | — | 2/3 | 3/3 | 1.8 s | 3.8 s | LOW: timeout: deadline 30000 ms ×1 | C35: does it pill under foundation? |
