# Adversarial eval (proof-plan §3)

2026-10-14 · `/srv/eval/sealed_sets/onboarding10_stt/live_X1.jsonl` · 45 cases × 1 runs · real UtterancePipeline per case (post-validation, merge, dedupe and corrections included).

**FAIL** · detection 86.7% (≥ 95%) · wrong HIGH 0 (0) · false alerts 6.7% (≤ 5%) · wrong correction texts 0 (0) · risky lines with an extra wrong alert 13.3% (≤ 5%)

Fact checker per line (retry included): p50 5784 ms · p95 17524 ms · 64 lines · timed-out calls 0 · retried lines 1 · lines without a completed check 0

Unverifiable lines with a soft fact note (not a false alert): 0

Caught means the expected rule or field, and the right value in a fact correction (D-197).

| type | risky caught | extra wrong alert | safe with an alert | HIGH | MEDIUM | fact note | wrong HIGH | wrong text |
|---|---|---|---|---|---|---|---|---|
| bundle_price | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| bundle_price_slip | 0/1 (0%) | 1/1 (100%) | - | 0 | 0 | 0 | 0 | 0 |
| bundle_volume | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| caution | - | - | 0/3 (0%) | 0 | 0 | 0 | 0 | 0 |
| checkout | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| cohost_bundle_question | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| cohost_medical_endorsement | 2/2 (100%) | 0/2 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| cohost_promo_question | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| cohost_viewer_correction | - | - | 0/2 (0%) | 0 | 0 | 0 | 0 | 0 |
| concentration_slip | 2/2 (100%) | 0/2 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| disease_prevention | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| filler | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| formula_equivalence | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| ingredient_amount | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| ingredient_disclosure | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| medical_claim | 2/2 (100%) | 1/2 (50%) | - | 0 | 0 | 0 | 0 | 0 |
| negation | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| permanent_effect | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| price | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| price_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| qualified_appearance_claim | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| scar_claim | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| split_caution | - | - | 1/1 (100%) | 0 | 0 | 1 | 0 | 0 |
| split_price | - | - | 1/1 (100%) | 0 | 0 | 1 | 0 | 0 |
| split_viewer_correction | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| storage | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| study_count_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| study_limit | - | - | 0/2 (0%) | 0 | 0 | 0 | 0 | 0 |
| study_population | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| study_provenance | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| superseded_promo_date | 0/1 (0%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| unverifiable_packaging | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| unverifiable_shelf_life | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| usage | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| usage_amount_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |
| variant_comparison | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| viewer_question | - | - | 0/1 (0%) | 0 | 0 | 0 | 0 | 0 |
| volume_slip | 1/1 (100%) | 0/1 (0%) | - | 0 | 0 | 0 | 0 | 0 |

## Missed risky lines

- X1-25 run 0 (bundle_price_slip): "The two 30 mL bottles in the bundle come to 76 Singapore dollars." → fact set_price 
- X1-31 run 0 (superseded_promo_date): "The scheduled closing date for this bundle is tonight, October 20th, 2026 at 11:59 p.m. Singapore time, unless allocated stock goes first." → none

## Alerts on safe lines

- X1-10 run 0 (split_caution): "And while you're using this in your routine, don't. / Skip your daytime sunscreen." → fact caution 
- X1-39 run 0 (split_price): "For the 50 mL single bottle, it's 50. / 4 Singapore dollars" → fact price 

## Wrong HIGH or wrong correction text

- none

## Extra wrong alerts on risky lines

- X1-05 run 0 (medical_claim): "If melasma is your concern, this serum helps treat it." → compliance asean-cosmetic-claims-guideline-appendix-iii-2007#2-d HIGH; fact test_result 
- X1-25 run 0 (bundle_price_slip): "The two 30 mL bottles in the bundle come to 76 Singapore dollars." → fact set_price 
