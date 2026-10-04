# Comment-flow eval

2026-10-05 · `comment_flow_cases.jsonl` · 12 scenarios × 1 runs · real runtime per scenario, events replayed on the wall clock.

**FAIL** · kind 100.0% (100%; short or odd 100.0%) · must_not_merge 0 (0) · route 80.0% (100%) · stale or wrong posts 9 (0) · host answers before confirm 1 (0) · cache reuse 84.6% (100%)

Clustering (mean per scenario): pairwise precision 97.0%, recall 73.7%.

Parallelism: first comment to verified draft p50 4.4s, p95 14.3s; triage alone p50 1.4s, p95 1.6s.

| scenario | run | kind | route | pairs P/R | must_not_merge | stale/wrong | host early | cache |
|---|---|---|---|---|---|---|---|---|
| CF01 | 0 | 13/13 | 3/7 | 100%/67% | 0 | 0 | 0 | 2/2 |
| CF02 | 0 | 13/13 | 10/13 | 100%/68% | 0 | 0 | 0 | 2/3 |
| CF03 | 0 | 13/13 | 10/12 | 100%/40% | 0 | 4 | 1 | 1/2 |
| CF04 | 0 | 13/13 | 12/12 | 100%/100% | 0 | 2 | 0 | 3/3 |
| CF05 | 0 | 13/13 | 9/12 | 100%/100% | 0 | 2 | 0 | 1/1 |
| CF06 | 0 | 13/13 | 9/12 | 100%/100% | 0 | 1 | 0 | 1/1 |
| CF07 | 0 | 12/12 | 12/12 | 100%/67% | 0 | 0 | 0 | 0/0 |
| CF08 | 0 | 12/12 | 12/12 | 100%/58% | 0 | 0 | 0 | 0/0 |
| CF09 | 0 | 12/12 | 6/12 | 100%/83% | 0 | 0 | 0 | 4/4 |
| CF10 | 0 | 12/12 | 7/12 | 100%/58% | 0 | 0 | 0 | 3/4 |
| CF11 | 0 | 12/12 | 11/12 | 64%/76% | 0 | 0 | 0 | 2/2 |
| CF12 | 0 | 12/12 | 11/12 | 100%/67% | 0 | 0 | 0 | 3/4 |

## Problems

- CF01 run 0: route cm_01M325108EGJ5847TWRWAEQQY3 (c_volume): HOST/needs_review (gold AUTO)
- CF01 run 0: route cm_01M325111BAF2FVZB1DBVJ9TZW (c_price): OPERATOR/needs_review (gold AUTO)
- CF01 run 0: route cm_01M32511KX6380M38V3YVF7010 (c_price): OPERATOR/needs_review (gold AUTO)
- CF01 run 0: route cm_01M325126FEQW9PEPDCEQZNFWN (c_price): OPERATOR/needs_review (gold AUTO)
- CF02 run 0: route cm_01M3250ZND29AQJB5F4YEYD8MQ (c_set_price): HOST/needs_review (gold AUTO)
- CF02 run 0: route cm_01M32511DJ3RJK3S1Q2SN2NN4N (c_set_price): HOST/needs_review (gold AUTO)
- CF02 run 0: route cm_01M32513RR4AV49Q7MB7V6T0Y1 (c_ampoule_price): OPERATOR/needs_review (gold AUTO)
- CF02 run 0: c_ampoule_price: 2 drafts for one question (cache not reused)
- CF03 run 0: route cm_01M32511KX24P5B8VAPSENNESY (c_oily): AUTO/answered (gold HOST)
- CF03 run 0: route cm_01M3253PYWZYZTA3YZCF0QK812 (c_dry): OPERATOR/needs_review (gold HOST)
- CF03 run 0: c_oily: posted 'No, the gel-cream texture is lightweight and absorbs quickly. Just use a smaller amount on oily areas.' missing ['Lightweight gel-cream texture that absorbs quickly.'] banned []
- CF03 run 0: c_oily: posted 'Yes. The gel-cream texture is lightweight and absorbs quickly, and you can use a smaller amount on oily areas.' missing ['Lightweight gel-cream texture that absorbs quickly.'] banned []
- CF03 run 0: c_oily: posted 'No, the gel-cream texture is lightweight and absorbs quickly. Just use a smaller amount on oily areas.' missing ['Lightweight gel-cream texture that absorbs quickly.'] banned []
- CF03 run 0: c_oily: posted 'Yes. The gel-cream texture is lightweight and absorbs quickly, and you can use a smaller amount on oily areas.' missing ['Lightweight gel-cream texture that absorbs quickly.'] banned []
- CF03 run 0: c_oily: host answer posted before the host confirmed
- CF03 run 0: c_oily: 2 drafts for one question (cache not reused)
- CF04 run 0: c_pregnant: posted 'The product has not been specifically tested on pregnant or breastfeeding women. Customers who are pregnant or breastfeeding should consult their doctor before use.' missing ['Pregnant or breastfeeding: not specifically tested. Consult a doctor before use.'] banned []
- CF04 run 0: c_pregnant: posted 'The product has not been specifically tested on pregnant or breastfeeding women. Customers who are pregnant or breastfeeding should consult their doctor before use.' missing ['Pregnant or breastfeeding: not specifically tested. Consult a doctor before use.'] banned []
- CF05 run 0: route cm_01M3251GNBQYG63T7P7RQ7QW9S (c_eczema): OPERATOR/needs_review (gold HOST)
- CF05 run 0: route cm_01M3251K0HJBNS7MD7Q3G94CQS (c_eczema): OPERATOR/needs_review (gold HOST)
- CF05 run 0: route cm_01M3251NBR0M9N69Z20PQ5DB1K (c_eczema): OPERATOR/needs_review (gold HOST)
- CF05 run 0: c_pregnant: posted 'The product has not been specifically tested on pregnant or breastfeeding women. Please consult your doctor before use.' missing ['Pregnant or breastfeeding: not specifically tested. Consult a doctor before use.'] banned []
- CF05 run 0: c_breastfeeding: posted 'The product has not been specifically tested on pregnant or breastfeeding women. Please consult your doctor before use.' missing ['Pregnant or breastfeeding: not specifically tested. Consult a doctor before use.'] banned []
- CF06 run 0: route cm_01M3252J088TFE3M494VYTNH2E (c_wrinkles): OPERATOR/needs_review (gold HOST)
- CF06 run 0: route cm_01M3252MHAW4PDP1DAZ228CNZ5 (c_wrinkles): OPERATOR/needs_review (gold HOST)
- CF06 run 0: route cm_01M3252Q2B1AQWYKKF2VDP57F6 (c_wrinkles): OPERATOR/needs_review (gold HOST)
- CF06 run 0: c_tingling: posted 'Sensitive skin may feel a mild, temporary tingling. Stop using and consult a dermatologist if redness, swelling or itching continues.' missing ['Sensitive skin may feel a mild, temporary tingling. Patch test first.'] banned []
- CF09 run 0: route cm_01M3253VCFYD01NSKYH2M8DSC5 (c_cream_pre): OPERATOR/closed (gold AUTO)
- CF09 run 0: route cm_01M3253W5V9V1HR86N6XZYFKQ1 (c_set_pre): HOST/closed (gold AUTO)
- CF09 run 0: route cm_01M3253WYRFVEC55ZBJHFSW402 (c_cream_pre): OPERATOR/closed (gold AUTO)
- CF09 run 0: route cm_01M3253XQNAVJRQT9GGED8BK4Z (c_set_pre): OPERATOR/closed (gold AUTO)
- CF09 run 0: route cm_01M3254XJP93TYZKGMYK5X1YJE (c_cream_pre): OPERATOR/closed (gold AUTO)
- CF09 run 0: route cm_01M3254YHF9HFR2K0WC06VPF9R (c_set_pre): OPERATOR/closed (gold AUTO)
- CF10 run 0: route cm_01M3253WC62G50HFBGX7YR1TZE (c_ampoule_sale): OPERATOR/closed (gold AUTO)
- CF10 run 0: route cm_01M3253X5KNDWAWY3HNNQFW9JZ (c_set_sale): HOST/closed (gold AUTO)
- CF10 run 0: route cm_01M3253XYGCBYJN0QDNVFAJ5N7 (c_ampoule_sale): OPERATOR/closed (gold AUTO)
- CF10 run 0: route cm_01M3255PZP3DQ9Q5MHHGTSMNRS (c_ampoule_sale): OPERATOR/closed (gold AUTO)
- CF10 run 0: route cm_01M325P923P7Z6C0D065CEM2NZ (c_set_live): HOST/needs_review (gold AUTO)
- CF10 run 0: c_set_live: 2 drafts for one question (cache not reused)
- CF11 run 0: route cm_01M3255R3T0BK5Z03JE0RVWETN (c_volume): OPERATOR/needs_review (gold AUTO)
- CF12 run 0: route cm_01M3258EC2BRSBSEV4HYC05XET (c_ampoule_fragrance): OPERATOR/needs_review (gold AUTO)
- CF12 run 0: c_cream_fragrance: 2 drafts for one question (cache not reused)
