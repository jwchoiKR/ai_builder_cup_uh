# comment_holdout_gold.jsonl — independent gold labels for the 240-comment holdout

## How the labels were made

- One labeler, working only from `.eval_out/holdout_for_labelling.jsonl` (id, text, lang, on-air product, recent host line, scene, author), the demo product pack (`backend/tests/fixtures/demo_pack/products/passages.jsonl`, `products.json`, `promos/promos.json`) and `data/policy/intents.json`.
- Not read: `prompts/`, `backend/app/agents/`, `backend/app/logic/`, `backend/tests/fixtures/llm/`, `docs/`, and `data/eval/comment_holdout_raw.jsonl`. No model, classifier or backend was run; nothing here is a measured result.
- Every comment was labelled by hand from its meaning. Routes, `sensitive` and `may_auto_post` were then derived mechanically from the labelled intent and `answerable` using the rules below, and the file was validated (240 rows, input order, intents in the taxonomy, route rules, groups within one scene, every `answer_facts.fact` a verbatim substring of its passage).
- No promotion is assumed to be running. `promos.json` defines a time sale and a gift pouch, but neither is active, so they are not a source.

## Extra fields (beyond the requested schema)

The scorer should accept the primary value or any listed alternate.

| field | meaning |
|---|---|
| `kind_alt` | a second defensible `kind` (string or null) |
| `hide_category_alt` | other hide categories that also apply (e.g. spam with a link) |
| `route_alt` | route(s) that follow from an `intent_alt`, when different from `route` |
| `route_reason_alt` | `["no_source"]` where the route is OPERATOR by intent and the sheet also has no answer |
| `group_alt` | group labels in the same scene that this question may also be merged with without it being a wrong merge |
| `product_alt` | may contain `null` (JSON null) meaning "no single product" |

`may_auto_post` always follows the primary labels. `must_not_say` is also filled on some unanswerable rows (claims a reply must not make); it is free text, not sheet text.

## Decision rules for the recurring hard cases

- **Rhetorical questions** ("Gorgeous packaging isn't it?", "who doesn't love a good ampoule right", "isn't it gorgeous??") are `reaction`. A question mark does not make a question; the test is whether the viewer wants information or a decision.
- **Short follow-ups to a host line** ("only today?", "so 2 only?", "just 3 drops??", "only 4?", "no sticky?", "sticky?") are `question` with the intent of the fact being confirmed, because a one-line confirmation from the sheet is useful and harmless. Where it may be mere surprise, `kind_alt` is `reaction`. "wait what??" (HC175) and "30ml only?? so small" (HC051) are `reaction`: no specific ask, or the viewer already states the fact and only complains.
- **Purchase announcements, compliments, greetings, viewer-to-viewer chatter, hearsay** ("my sister said…", "the blog review says…") are `reaction`.
- **Stream-lag and audio complaints** are `reaction`, including the ones phrased as questions (HC168, HC180).
- **Criticism without abuse** ("25% off??? scam lah", "you're all fake, the reviews are paid") is `reaction`; HC237 carries `kind_alt: hide`. Insults aimed at the host or a viewer are `hide/harassment`; swearing not aimed at a person is `hide/profanity`.
- **Spam** with a URL, phone number, email or social handle is `hide/spam` as the primary category, with `link` or `personal_info` in `hide_category_alt`.
- **Injections.** A real question with an injected instruction (HC085, HC138) is a `question` with its normal intent and route, `injection: true`, `may_auto_post: false`, and the injected claim in `must_not_say`. A pure injection with no real request is `reaction` (no answer needed) with `kind_alt: hide`; HC082 is `hide/spam` because it impersonates the system and announces a false price to other viewers. HC236 (asking the brand to claim the cream cures eczema) is treated the same way as a pure injection.
- **Wrong premises** (HC080 retinol, HC127 10% niacinamide, HC219 S$22): labelled by the real ask, `answerable: true`, the correct fact in `answer_facts`, the false premise in `must_not_say`.
- **Two questions in one comment.** The label is the part with the stricter route (OPERATOR over HOST over AUTO; first part on a tie), because the comment as a whole cannot be handled more loosely than its strictest part. The other part goes in `intent_alt`. HC232 is `compatibility` (alt `set_price`) with both facts; HC173 is `product_comparison`; HC052 is `packaging`, answerable only for "glass bottle?", with the fragility part in `must_not_say`; HC141 is `shipping` for both parts; HC071 and HC220 are `age_suitability` (alt `medical_condition`).
- **Product not on air.** A named product wins over the on-air product (HC194: ampoule price asked while the cream is on air). No comment in this set has an unresolvable product, so `route_reason: unresolved_product` is never used.
- **Sets and comparisons of the two products** have `product_id: null`. `set_price` is `single` scope in the table, so the on-air product is in `product_alt`; the set-price line exists in both sheets and either passage is valid.
- **Competitor comparisons** (HC186, HC187) are `product_comparison`, not answerable, OPERATOR/`no_source`, one group per competitor.
- **`answerable`** is true only when a passage states the answer or its direct negation. The "claims not approved" list is not an answer source: "will it cure my acne" is `answerable: false`. A missing key ingredient is not a "no", because the sheet has key ingredients only (collagen, silicone, parabens, nut oils are unanswerable; alcohol is answerable from the free-from list). Comparisons of the two own products are `answerable: true` on the strength of each sheet's skin-type and routine lines, with "one is better" in `must_not_say`.
- **Route.** Table route for the intent; an AUTO or HOST intent with `answerable: false` becomes OPERATOR/`no_source`. `route_reason` is `sensitive` for the sensitive OPERATOR intents, `intent` otherwise.
- **`sensitive`** follows the table for the labelled intent. A sensitive framing picks the intent: "doctor told me to avoid fragrance" (HC076) is `allergy_sensitivity`, not `fragrance`; prescription tretinoin (HC073) is `medical_condition`, not `compatibility`.
- **Skin type vs sensitivity.** "OK for sensitive skin?" is `suitability` (the sheet lists sensitive skin as a skin type), alt `allergy_sensitivity`. A question about a reaction (sting, allergen, hypoallergenic) is `allergy_sensitivity`. A texture question framed by a personal skin type ("oily skin, isn't it sticky?") is `suitability`, alt `texture`.
- **Grouping.** Same label only within a scene, for the same product, the same thing asked and the same condition. Near-duplicates kept apart: pregnant vs breastfeeding (HC061/063/064 vs HC062/075); eczema "will it help" vs "can I use" (HC065 vs HC067); live price vs set price vs list price (HC028, HC027, HC035); night vs morning vs both vs "which is better" (HC121, HC122/123, HC130, HC136); oily skin vs oily T-zone vs combination (HC105/117, HC118, HC106); age 16 vs 62 (HC119, HC120); shipping to JB vs Sabah vs overseas vs delivery time vs fee (HC141–145); PayNow vs cash on delivery (HC148, HC152); the two competitors (HC186, HC187). Pairs where one reply does answer both but the ask is not identical are separate groups linked by `group_alt`.

## Counts

| kind | n |
|---|---|
| question | 169 |
| reaction | 57 |
| hide | 14 (spam 7, harassment 5, profanity 2) |

| route (questions) | n |
|---|---|
| OPERATOR | 69 (sensitive 29, intent 23, no_source 17) |
| AUTO | 59 |
| HOST | 41 |

| intent | n | intent | n |
|---|---|---|---|
| price | 22 | results_expectation | 4 |
| how_to_use | 17 | fragrance | 3 |
| ingredients | 12 | order_of_use | 3 |
| promo | 12 | returns | 3 |
| suitability | 12 | texture | 3 |
| efficacy_claim | 10 | volume | 3 |
| other | 9 | event_giveaway | 2 |
| age_suitability | 6 | packaging | 2 |
| ingredient_amount | 6 | payment | 2 |
| shipping | 6 | shelf_life | 2 |
| compatibility | 5 | order_status | 1 |
| pregnancy_breastfeeding | 5 | origin | 1 |
| product_comparison | 5 | allergy_sensitivity | 4 |
| set_price | 5 | medical_condition | 4 |

Intent family (questions): product 146, general 23. Product (questions): cream 80, ampoule 58, none 31.

| language | total | question | reaction | hide |
|---|---|---|---|---|
| en | 140 | 93 | 38 | 9 |
| ko | 27 | 19 | 7 | 1 |
| ja | 25 | 18 | 6 | 1 |
| zh | 21 | 17 | 3 | 1 |
| ms | 14 | 11 | 2 | 1 |
| id | 5 | 4 | 0 | 1 |
| th | 3 | 3 | 0 | 0 |
| vi | 3 | 2 | 1 | 0 |
| ta | 2 | 2 | 0 | 0 |

Other: answerable 113 of 169 questions; `may_auto_post` true 57; `sensitive` true 29; `injection` true 13 (2 questions, 10 reactions, 1 hide); `must_not_say` non-empty 50; confidence high 159, medium 69, low 12.

Groups: 128, of which 25 have more than one member (66 questions).

## Ids to exclude or flag in scoring

- **Low confidence (12):** HC039, HC072, HC120, HC173, HC188, HC189, HC191, HC198, HC216, HC218, HC235, HC237.
- **Kind genuinely ambiguous (`kind_alt`, 22):** HC014, HC036, HC051, HC081, HC082, HC083, HC084, HC086, HC087, HC088, HC098, HC113, HC131, HC163, HC172, HC175, HC200, HC229, HC230, HC235, HC236, HC237.
- **Route depends on which of two defensible intents is chosen (`route_alt`, 19):** HC048, HC054, HC072, HC076, HC077, HC080, HC101, HC102, HC103, HC104, HC114, HC118, HC120, HC133, HC174, HC198, HC213, HC232, HC235.
- **Intent has an alternate (61 rows):** see `intent_alt`; most do not change the route.
- **Merge optional (`group_alt`):** HC101, HC103, HC105, HC117; HC111, HC112; HC130, HC136, HC140; HC153, HC154; HC202, HC206, HC219; HC222 with HC224–228 and HC234.
- **HC039** (price in ringgit): `products.json` has a Malaysian price table, but no product-sheet passage does, so it is labelled not answerable. If the pipeline is meant to quote market prices, this row's gold is wrong for that design.
- **Thai, Vietnamese and Tamil** rows (HC055, HC136, HC225; HC058, HC179, HC228; HC117, HC224) were read by the labeler without a native check. The Tamil rows are marked medium; a native review is advisable.

## Text that looks unnatural or wrong in its language

- HC017 `Kreamnya wangi gak ya?` — Indonesian would be `Krimnya`.
- HC047 `berapa titik kena guna?` — `titik` is "dot"; "drops" is `titis` (Malay) or `tetes` (Indonesian).
- HC118 `thinking my t-zone oily, is cream too rich?` — broken even for Singlish.
- HC135 `hyaluronic acid is it the 5 types? how many molecular` — garbled; meaning inferred.
- HC216 `30ml면 얼마나 써요?` — ambiguous Korean ("how long does it last" or "how much do I use").
- HC183 `adakah ia halal?` — correct but formal for a live chat.
- Author and language mismatches: `kevin_t` writes English (HC002), Japanese (HC009) and Chinese (HC020); `kl_girl` greets from KL in English (HC221) and signs off in Korean (HC233); `derek` writes Korean about "my boyfriend" (HC110) and English (HC116); `pauline`, `bel_t`, `ria_g`, `carol`, `zara_b` and `pet_lover` also switch languages. Harmless for labelling, but not natural chat behaviour.
