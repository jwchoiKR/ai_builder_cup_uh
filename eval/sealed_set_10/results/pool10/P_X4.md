# Adversarial eval (proof-plan §3)

2026-10-14 · `/srv/eval/sealed_sets/onboarding10_stt/live_X4.jsonl` · 45 cases × 1 runs · real UtterancePipeline per case (post-validation, merge, dedupe and corrections included).

**FAIL** · detection 73.3% (≥ 95%) · wrong HIGH 0 (0) · false alerts 3.3% (≤ 5%) · wrong correction texts 1 (0) · risky lines with an extra wrong alert 20.0% (≤ 5%)

Fact checker per line (retry included): p50 7768 ms · p95 37328 ms · 76 lines · timed-out calls 2 · retried lines 2 · lines without a completed check 2

Unverifiable lines with a soft fact note (not a false alert): 0

Caught means the expected rule or field, and the right value in a fact correction (D-197).

| type | risky caught | extra wrong alert | safe with an alert | HIGH | MEDIUM | fact note | wrong HIGH | wrong text |
|---|---|---|---|---|---|---|---|---|
| bundle_addon_promo_error | 0/1 (0%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 1 |
| bundle_price | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| bundle_price_slip | 0/1 (0%) | 1/1 (100%) | - | 0 | 0 | 0 | 0 | 0 |
| caution | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| cell_restoration_claim | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| checkout | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| cohost_addon_correction | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| cohost_bundle_exclusion | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| cohost_bundle_question | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| cohost_hair_growth_endorsement | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| cohost_medical_endorsement | 1/1 (100%) | 1/1 (100%) | - | 0 | 0 | 0 | 0 | 0 |
| cohost_promo_question | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| concentration_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| eligible_order | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| filler | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| gift_identity | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| gift_quantity_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| gift_volume_slip | 0/1 (0%) | 1/1 (100%) | - | 0 | 0 | 0 | 0 | 0 |
| hair_loss_claim | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| ingredient_amount | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| ingredient_disclosure | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| medical_claim | 2/2 (100%) | 0/2 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| negation | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| permanent_effect | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| price | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| promo_calculation | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| promo_date_slip | 0/1 (0%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| promo_exchange | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| promo_exclusion | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| promo_schedule | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| promo_threshold_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| qualified_appearance_claim | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| retail_volume_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| split_caution | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| split_price | - | - | 1/1 (100%) | 0 | 0 | 1 | 0 | 0 |
| split_viewer_correction | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| standard_bundle_price | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| study_limit | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| study_provenance | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| study_schedule | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| study_timing | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| unverifiable_gift_price | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| unverifiable_shelf_life | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| usage | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |

## Missed risky lines

- X4-03 run 0 (bundle_price_slip): "두 병 묶음 한 세트 가격은 46 싱가포르 달러입니다." → fact set_price 
- X4-20 run 0 (gift_volume_slip): "증정 대상 주문에 드리는 여행용 샴푸는 50ml예요." → fact promo 
- X4-37 run 0 (promo_date_slip): "여행용 증정의 예정 마감은 오늘 2026년 10월 20일 밤 11시 59분 싱가포르 시간이에요. / 재고가 먼저 소진되면 더 일찍 끝나고요." → none
- X4-42 run 0 (bundle_addon_promo_error): "묶음에 단품 한 병을 추가하면 합계 65 싱가포르 달러라 여행용 한 개를 받으실 수 있어요. / 인사 기간 안에 결제하고 재고가 남아있으면요." → fact promo 

## Alerts on safe lines

- X4-39 run 0 (split_price): "단품 두 병을 각각 담으면 40 / 6 싱가포르 달러예요." → fact price 

## Wrong HIGH or wrong correction text

- X4-42 run 0 (bundle_addon_promo_error): "묶음에 단품 한 병을 추가하면 합계 65 싱가포르 달러라 여행용 한 개를 받으실 수 있어요. / 인사 기간 안에 결제하고 재고가 남아있으면요." → fact promo 

## Extra wrong alerts on risky lines

- X4-03 run 0 (bundle_price_slip): "두 병 묶음 한 세트 가격은 46 싱가포르 달러입니다." → fact set_price 
- X4-20 run 0 (gift_volume_slip): "증정 대상 주문에 드리는 여행용 샴푸는 50ml예요." → fact promo 
- X4-35 run 0 (cohost_medical_endorsement): "시청자분이 두피 건선 치료에도 도움이 되냐고 하세요. / 네, 이 샴푸가 두피 건선 치료에도 도움을 줘요." → compliance asean-cosmetic-claims-guideline-appendix-iii-2007#2-d HIGH; fact other 
