# Adversarial eval (proof-plan §3)

2026-10-16 · `/home/jaewoo/eval1017/repo_1017/eval/sealed_set_10/onboarding10_stt/live_X2.jsonl` · 45 cases × 1 runs · real UtterancePipeline per case (post-validation, merge, dedupe and corrections included).

**FAIL** · detection 93.3% (≥ 95%) · wrong HIGH 0 (0) · false alerts 0.0% (≤ 5%) · wrong correction texts 0 (0) · risky lines with an extra wrong alert 0.0% (≤ 5%)

Fact checker per line (retry included): p50 2662 ms · p95 24546 ms · 68 lines · timed-out calls 1 · retried lines 1 · lines without a completed check 1

Unverifiable lines with a soft fact note (not a false alert): 0

Caught means the expected rule or field, and the right value in a fact correction (D-197).

| type | risky caught | extra wrong alert | safe with an alert | HIGH | MEDIUM | fact note | wrong HIGH | wrong text |
|---|---|---|---|---|---|---|---|---|
| approved_cosmetic_purpose | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| caution | - | - | 0/3 (0%) | 0 | 0 | 0 | 0 | 0 |
| checkout | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| cohost_disclosure_question | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| cohost_medical_endorsement | 2/2 (100%) | 0/2 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| cohost_price_question | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| cohost_study_correction | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| cohost_viewer_correction | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| concentration_slip | 2/3 (67%) | 0/3 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| expired_price | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| filler | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| historical_price | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| ingredient_amount | - | - | 0/2 (0%) | 0 | 0 | 0 | 0 | 0 |
| ingredient_disclosure | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| ingredient_total | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| medical_claim | 3/3 (100%) | 0/3 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| negation | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| physiological_antiageing | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| price | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| qualified_hydration_claim | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| scar_claim | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| split_caution | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| split_price | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| split_viewer_correction | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| study_conditions | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| study_count_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| study_limit | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| study_method | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| study_metric_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| study_provenance | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| study_timing | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| study_timing_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| unverifiable_fragrance | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| unverifiable_shelf_life | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| usage | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| viewer_caution_question | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| volume_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |

## Missed risky lines

- X2-14 run 0 (concentration_slip): "세라마이드 NP 하나만 0.17% 들어있어요." → none

## Alerts on safe lines

- none

## Wrong HIGH or wrong correction text

- none

## Extra wrong alerts on risky lines

- none
