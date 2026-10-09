# comment_holdout2_gold — second held-out comment set (240 comments)

Gold labels for `.eval_out/holdout2_for_labelling.jsonl` (HD001–HD240, 12 scenes of 20 comments).
This set is meant to be run once. No accuracy numbers are given here; no model was run.

## How the labels were made

- Labelled by an independent labeler from the meaning of each comment only. Inputs read:
  the 240 comments (`id, text, lang, on_air_product_id, recent_host_line, scene, author`),
  `backend/tests/fixtures/demo_pack/products/passages.jsonl`, `products.json`, `promos/promos.json`,
  `brand_rules.json`, and `data/policy/intents.json`, plus the owner conventions 1–9 from the task.
- Not read: `prompts/`, `backend/app/`, `backend/scripts/`, `backend/tests/fixtures/llm/`, `docs/`,
  `comment_holdout2_raw.jsonl` (author hints), and the first held-out set's raw, gold, README and rulings files.
- Every comment was labelled by hand in one pass in scene order, then cross-checked scene by scene for
  duplicates (including cross-language ones). `route`, `route_reason`, `sensitive` and `may_auto_post`
  are derived mechanically from `intent` + `answerable` (rule below), so they cannot disagree with the table.
- `answer_facts[].fact` is a verbatim substring of the cited passage (checked by script).
- No promotion is assumed to be running: the gift pouch and time sale in `promos.json` are not answer sources.

## Derived fields (mechanical rule)

| case | route | route_reason |
|---|---|---|
| intent is sensitive in `intents.json` | OPERATOR | sensitive |
| intent's own route is OPERATOR (shipping, returns, payment, order_status, event_giveaway, other, certification, clinical_results) | OPERATOR | intent |
| AUTO/HOST intent, sheet cannot answer | OPERATOR | no_source |
| AUTO/HOST intent, sheet answers | table route | intent |

`may_auto_post = route == AUTO and not sensitive and answerable`. `unresolved_product` was never needed.
For an intent that is already OPERATOR, an unanswerable question keeps `route_reason: intent` (or `sensitive`),
not `no_source`. `route_alt` lists the other route when `answerable` itself is a close call.

## Decision rules for recurring hard cases

1. **Health first (convention 4).** A stated reaction history, medicine, procedure, pregnancy, breastfeeding
   or a named age moves the question to the health intent even when the face question is a plain fact
   (HD014, HD015, HD022: alcohol / niacinamide strength asked by someone who reacts). The plain-fact intent is
   kept in `intent_alt`, and the plain-fact twin in the same scene is kept in `group_alt`.
2. **Skin type is not health.** Oily, dry, flaky, sensitive-as-a-type, "dry patches in winter" are `suitability`
   (HD008–HD010, HD088, HD133, HD202).
3. **Over-the-counter actives are compatibility, prescribed or clinic items are medical.** Vitamin C, AHA toner,
   retinol 0.5%, foundation: `compatibility` (HD032–HD034, HD226–HD228). Dermatologist ointment, isotretinoin,
   peel, laser, acne under treatment: `medical_condition` (HD042, HD043, HD046, HD059, HD149).
4. **Efficacy claims on the "Claims not approved" list are labelled answerable**, with the not-approved sentence
   as the fact (ageing HD044/HD060, whitening HD142–HD144, dark spots HD141, acne scars HD147, rosacea HD041).
   The grounded reply is "this is not something the product claims". They are sensitive, so never auto-posted.
   A claim the list does not mention is unanswerable (chickenpox scars on the cream sheet HD045, pores HD145).
5. **Personal medical fit is unanswerable** unless the sheet addresses it directly. Pregnancy and breastfeeding
   are answerable (not tested, consult a doctor). Peel, laser, medicines, children, teens, age 70+ are not.
6. **Follow-ups to the host line (convention 7)** are questions when they ask for confirmation or more detail
   (HD012, HD027, HD053, HD075, HD087, HD108, HD109, HD154, HD175, HD210, HD233) and reactions when they only
   express surprise (HD134 "from 48?? wow"). `kind_alt` carries the other reading.
7. **Remarks about known facts are reactions** even with a question mark (HD005, HD035, HD150, HD155), as is
   passing on hearsay (HD058, HD199, HD218). Hearsay followed by a direct ask is a question (HD093, HD163).
8. **Wrong premises**: answered with the true fact, and the false premise goes in `must_not_say`
   (S$25 HD127, 100 ml HD128, 250 ml HD220, 15% niacinamide HD118, 5% centella HD119, tub HD092, 3 drops per
   side HD027, fish collagen HD131, free pouch HD077, plus the injected claims in HD080, HD191, HD197, HD198).
9. **Foreign currency (convention 6)**: `price`, answerable, auto-postable, `condition: "price in another currency"`.
   Kept as its own group, with the plain-price group in `group_alt` where one exists (HD073, HD074, HD130).
10. **Discount terms vs amount**: how much = `price`; when the live price ends, who gets it, codes, gifts = `promo`
    (HD072, HD075, HD133 second part, HD135, HD061, HD062, HD077, HD233), with `price` in `intent_alt` where close.
11. **Full ingredient list** (HD203–HD205) and "contains X?" for an X the sheet never mentions (HD104, HD115,
    HD131) are unanswerable: the sheet has key ingredients and a free-from line only. "Contains X?" for a listed
    or free-from X is answerable (HD024, HD206, HD208).
12. **Grouping**. Same label only for same scene, intent, product and no differing condition. When two
    questions differ by a condition but one reply would plausibly serve both, they are separate groups that
    name each other in `group_alt` (oily vs oily T-zone HD008/HD009; vitamin C vs vitamin C in the morning
    HD032+HD034/HD033; set price vs "is the set cheaper" HD124+HD126/HD125; sale end time vs "only today?"
    HD072/HD075; sample size confirmation vs adequacy HD053/HD048; after-opening vs unopened shelf life
    HD229+HD231/HD230).
13. **`condition`** is one short lowercase phrase. Besides personal conditions it also carries the
    combined-with product and the time of day when they change the answer ("with vitamin c serum, morning").
14. **`product_id`**: named product, else on-air for single-product intents; `null` for general intents, for the
    set (`set_price`, `product_alt` lists both products) and for cream-vs-ampoule comparisons.
15. **Hide category** (single field, no alt): URL present = `link`; phone number or email = `personal_info`;
    advert or bot order without those = `spam`; insult aimed at a person or the sellers = `harassment`;
    swear word = `profanity`. HD019, HD078 (`link`) and HD138, HD184 (`personal_info`) could equally be `spam`;
    HD037 (`profanity`) could equally be `harassment`. Negative opinions without an insult stay reactions
    (HD016, HD187, HD190), with `hide` in `kind_alt` for HD016 and HD190.
16. **Two-question comments (convention 8)**: the part needing a person more is primary; `answer_facts` and
    `group` describe the primary only. When both parts are plain facts the first asked is primary (HD132).
17. **Injection (convention 2)**: order only = hide/spam/injection (9 comments); order plus real question =
    question with `signal: injection` (HD080, HD191, HD197, HD198). Only HD198 may be auto-posted.

## Counts

| kind | n | | signal | n |
|---|---|---|---|---|
| question | 170 | | none | 220 |
| reaction | 46 | | injection | 13 (9 hide, 4 question) |
| hide | 24 | | stream_issue | 7 |

Hide categories: spam 10 (9 of them injection), harassment 6, link 4, personal_info 2, profanity 2.

Intents (170 questions): price 13, how_to_use 11, clinical_results 9, ingredients 9, efficacy_claim 8, promo 8,
ingredient_amount 7, shipping 7, compatibility 6, medical_condition 6, other 6, payment 6, returns 6,
suitability 6, allergy_sensitivity 5, pregnancy_breastfeeding 5, results_expectation 5, texture 5,
age_suitability 4, set_price 4, shelf_life 4, specification 4, volume 4, certification 3, event_giveaway 3,
order_of_use 3, order_status 3, origin 3, product_comparison 3, fragrance 2, packaging 2. All 31 intents occur.

Routes: OPERATOR 97, AUTO 47, HOST 26. Route reasons: intent 116, sensitive 28, no_source 26.
Answerable 97 / not answerable 73. `may_auto_post` true 47. Sensitive 28.
Product: cream 67, ampoule 65, null 38.

Language (input `lang` field): en 186, ja 16, ko 15, zh 13, ms 10.

| lang | question | reaction | hide |
|---|---|---|---|
| en | 124 | 43 | 19 |
| ja | 14 | 1 | 1 |
| ko | 12 | 1 | 2 |
| zh | 12 | 0 | 1 |
| ms | 8 | 1 | 1 |

Confidence: high 173, medium 56, low 11. Each scene has 20 comments.

## Groups

143 groups, 18 with more than one member:

| group | intent | members |
|---|---|---|
| s01_cream_open-1 | price | HD002, HD003, HD004 |
| s02_ampoule_open-11 | compatibility | HD032, HD034 |
| s02_ampoule_open-13 | price | HD039, HD040 |
| s03_cream_sensitive-10 | certification | HD050, HD051, HD052 |
| s04_ampoule_deal-4 | shipping | HD064, HD080 |
| s04_ampoule_deal-13 | price | HD073, HD074 |
| s05_cream_howto-1 | how_to_use | HD081, HD082, HD083 |
| s06_ampoule_specs-5 | origin | HD105, HD106, HD107 |
| s06_ampoule_specs-11 | results_expectation | HD113, HD114 |
| s07_cream_price_mix-1 | price | HD122, HD127, HD140 |
| s07_cream_price_mix-3 | set_price | HD124, HD126 |
| s08_ampoule_effects-2 | efficacy_claim | HD142, HD143, HD144 |
| s08_ampoule_effects-8 | clinical_results | HD151, HD153 |
| s09_cream_chatter-7 | texture | HD177, HD178 |
| s11_cream_mixed-3 | ingredients | HD203, HD204, HD205 |
| s11_cream_mixed-9 | returns | HD211, HD212, HD213 |
| s12_ampoule_close-1 | event_giveaway | HD221, HD222, HD223 |
| s12_ampoule_close-7 | shelf_life | HD229, HD231 |

## Low-confidence ids

HD007, HD028, HD056, HD079, HD089, HD102, HD111, HD129, HD145, HD146, HD176.
It would be reasonable to score these leniently or leave them out of the headline number.

## Two-question comments

HD020, HD028, HD086, HD110, HD132, HD133, HD173, HD237.
(HD080, HD191, HD197, HD198 are one question plus an injected order, not two questions.)

## Text that looks unnatural or mislabelled in its language

- HD189: the text is Malay ("bodoh betul host ni, pergi mampus la") but `lang` is `en`. A `comment_en` is given.
- HD070 (zh): "有没有开发票或者收据" is slightly off; "可以开发票吗" / "有没有发票或收据" would be natural.
- HD034 (zh): "叠加" for layering skincare is understandable but "叠涂" / "一起用" is more usual.
- HD103 (ms): mixes formal "adakah" with colloquial "ni"; reads a little stiff.
- HD126 (ja): correct but formal for live chat.
- Traditional characters in HD046, HD105, HD211 and simplified elsewhere is natural for a mixed audience.

## Boundaries still hard to decide

- **`answerable` for not-approved claims** (HD041, HD044, HD060, HD141–HD144, HD147). I labelled them answerable
  because the sheet states the claim is not one the product makes; a stricter reading ("the sheet does not say
  whether it works") makes them unanswerable. The route is OPERATOR either way.
- **efficacy_claim vs results_expectation** for cosmetic outcomes: whitening (HD142–HD144), dark spots (HD141),
  pores (HD145), "does it actually work" (HD146).
- **allergy_sensitivity vs suitability vs ingredients** when a reaction is mentioned in passing: HD014 (skin
  reddens easily), HD148 (tingling on sensitive skin, not the viewer's own history).
- **age_suitability for an elderly user** (HD031): fits the name, but the convention lists babies and children.
- **Partial answers.** The sheet answers part of what is asked: night-only use (HD089), how quick is quick
  (HD087), gel-cream vs normal cream (HD177, HD178) vs lotion (HD179), does 1% ceramide matter (HD176), when the
  sale ends (HD072), same price as the website (HD209), full ingredient list (HD203–HD205), post-peel skin
  against "broken or damaged skin" (HD042), safe after a past rash (HD047), smell despite "no added fragrance"
  on the ampoule (HD116).
- **price vs promo** for the terms of the live price (HD072, HD075, HD135, HD209) and **promo vs set_price** for
  "buy two" (HD129).
- **Questions with no clean intent**: how long a tube lasts (HD007), batch code / authenticity (HD102), flying
  with the bottle (HD110, HD111), live vs website (HD079), is the shop legit (HD163), questions to the host about
  herself (HD169, HD170).
- **question vs reaction**: nudge about an unanswered question (HD056), sceptical remark on a figure (HD035),
  jokes with a question shape (HD150, HD162, HD226), shout-out request (HD217), short surprised follow-ups
  (HD012, HD053, HD108, HD134).
- **hide vs reaction** for rude but non-abusive criticism (HD016, HD096, HD188, HD190), and the single
  `hide_category` for adverts that carry a link or contact detail (rule 15).
- **Group strictness** when only one of two near-duplicates states a condition (rule 12 pairs).
