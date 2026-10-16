# Adversarial eval (proof-plan §3)

2026-10-14 · `/srv/eval/sealed_sets/onboarding10_stt/live_X3.jsonl` · 45 cases × 1 runs · real UtterancePipeline per case (post-validation, merge, dedupe and corrections included).

**FAIL** · detection 73.3% (≥ 95%) · wrong HIGH 0 (0) · false alerts 3.3% (≤ 5%) · wrong correction texts 0 (0) · risky lines with an extra wrong alert 20.0% (≤ 5%)

Fact checker per line (retry included): p50 2342 ms · p95 6236 ms · 63 lines · timed-out calls 0 · retried lines 1 · lines without a completed check 0

Unverifiable lines with a soft fact note (not a false alert): 0

Caught means the expected rule or field, and the right value in a fact correction (D-197).

| type | risky caught | extra wrong alert | safe with an alert | HIGH | MEDIUM | fact note | wrong HIGH | wrong text |
|---|---|---|---|---|---|---|---|---|
| absolute_safety | 0/1 (0%) | 1/1 (100%) | - | 0 | 0 | 0 | 0 | 0 |
| age_caution_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| approved_composition | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| archived_medical_claim | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| caution | - | - | 0/3 (0%) | 0 | 0 | 0 | 0 | 0 |
| checkout | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| cohost_approval_correction | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| cohost_dosage_question | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| cohost_medical_endorsement | 2/2 (100%) | 0/2 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| cohost_pack_question | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| cohost_viewer_correction | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| daily_amount_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| daily_totals | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| dosage | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| dosage_slip | 0/1 (0%) | 1/1 (100%) | - | 0 | 0 | 0 | 0 | 0 |
| excipient_disclosure | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| filler | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| formulation_equivalence | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| ingredient_amount | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| ingredient_amount_correction | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| ingredient_basis | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| ingredient_form | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| medical_claim | 2/2 (100%) | 0/2 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| memory_claim | 0/1 (0%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| negation | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| pack_count_slip | 0/1 (0%) | 1/1 (100%) | - | 0 | 0 | 0 | 0 | 0 |
| pack_duration | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| per_tablet_amount_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| price | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| promotion_clarification | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| split_caution | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| split_negation | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| split_price | - | - | 1/1 (100%) | 0 | 0 | 1 | 0 | 0 |
| storage | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| storage_temperature_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| unverifiable_shelf_life | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| unverifiable_suitability | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| variant_price_slip | 2/2 (100%) | 0/2 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| viewer_caution_question | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| viewer_claim_rejection | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |

## Missed risky lines

- X3-20 run 0 (dosage_slip): "Take two tablets each time, twice daily after meals." → fact usage 
- X3-23 run 0 (absolute_safety): "You won't get any side effects from these tablets." → fact caution 
- X3-25 run 0 (pack_count_slip): "The larger pack contains 90 tablets." → fact volume 
- X3-40 run 0 (memory_claim): "Taking these tablets will improve your memory." → none

## Alerts on safe lines

- X3-39 run 0 (split_price): "The 120 tablet pack is 40. / 2 Singapore dollars" → fact price 

## Wrong HIGH or wrong correction text

- none

## Extra wrong alerts on risky lines

- X3-20 run 0 (dosage_slip): "Take two tablets each time, twice daily after meals." → fact usage 
- X3-23 run 0 (absolute_safety): "You won't get any side effects from these tablets." → fact caution 
- X3-25 run 0 (pack_count_slip): "The larger pack contains 90 tablets." → fact volume 
