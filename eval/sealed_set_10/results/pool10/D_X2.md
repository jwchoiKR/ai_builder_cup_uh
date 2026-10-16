# Adversarial eval (proof-plan §3)

2026-10-14 · `/srv/eval/sealed_sets/onboarding10_stt/live_X2.jsonl` · 45 cases × 1 runs · real UtterancePipeline per case (post-validation, merge, dedupe and corrections included).

**FAIL** · detection 80.0% (≥ 95%) · wrong HIGH 0 (0) · false alerts 0.0% (≤ 5%) · wrong correction texts 1 (0) · risky lines with an extra wrong alert 6.7% (≤ 5%)

Fact checker per line (retry included): p50 2192 ms · p95 5360 ms · 68 lines · timed-out calls 0 · retried lines 0 · lines without a completed check 0

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
| concentration_slip | 1/3 (33%) | 0/3 (0%) | - | 0 | 0 | 0 | 0 | 1 |
| expired_price | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| filler | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| historical_price | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| ingredient_amount | - | - | 0/2 (0%) | 0 | 0 | 0 | 0 | 0 |
| ingredient_disclosure | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| ingredient_total | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| medical_claim | 3/3 (100%) | 1/3 (33%) | - | 0 | 0 | 0 | 0 | 0 |
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
| study_timing_slip | 0/1 (0%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| unverifiable_fragrance | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| unverifiable_shelf_life | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| usage | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| viewer_caution_question | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| volume_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |

## Missed risky lines

- X2-14 run 0 (concentration_slip): "세라마이드 NP 하나만 0.17% 들어있어요." → fact ingredient_amount 
- X2-31 run 0 (study_timing_slip): "그 수분 시험은 마지막 사용 1시간 뒤에 측정한 거예요." → none
- X2-37 run 0 (concentration_slip): "세라마이드 AP는 0.1% 들어있어요." → none

## Alerts on safe lines

- none

## Wrong HIGH or wrong correction text

- X2-14 run 0 (concentration_slip): "세라마이드 NP 하나만 0.17% 들어있어요." → fact ingredient_amount 

## Extra wrong alerts on risky lines

- X2-05 run 0 (medical_claim): "이 크림은 습진 치료에도 도움을 줘요." → fact test_result ; compliance asean-cosmetic-claims-guideline-appendix-iii-2007#2-d HIGH
