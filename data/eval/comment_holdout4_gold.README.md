# comment_holdout4_gold — fourth held-out comment set (240 comments, 12 scenes)

Ids HF001..HF240, scenes H4S01..H4S12, group ids `H4Sxx-n`. Same row schema, value vocabulary and decision
rules as `comment_holdout3_gold.README.md`; this file only lists what is new or different, the counts and
the rows the labeler was unsure about.

## How the labels were made

- Inputs read: `comment_holdout4_raw.jsonl`, the demo product pack in `.eval_out/data/` (`products.json`,
  `passages.jsonl`, the two `.md` sheets, `promos.json`), `data/policy/intents.json`,
  `comment_holdout_rulings.json`, and set 3's README, gold and raw files (for the schema and conventions).
- Not read: prompts, backend agents/pipelines/logic, `docs/comments.md`, `docs/eval/`, any system output.
- The raw file's `note` column was visible but was not used as a label; every comment was judged from its
  text, its scene, its author's earlier comments and the host line.
- Labels were written by hand per comment and emitted by a script that runs the checks listed at the end.
- No time sale or gift promotion is assumed to be running (no `recent_host_line` in this set announces one).
  The price in force is the live broadcast price.

## What is different from set 3

1. **Two-question comments.** The owner's rule for this set is explicit: a comment with two questions waits
   for a person. Set 3 had no comment with two plain, answerable parts. Here HF087 (set price + "can I buy
   singly") and HF006 (size + "how long") are labelled `needs_approval: true`. The reason vocabulary has no
   value for "two questions", so `unclear` is used, with `needs_approval_alt: true`. HF071 ("daytime? need
   sunscreen?") is kept as one usage question because one FAQ entry answers both parts (low confidence).
2. **Time-sale prices quoted by viewers** (HF065 "S$28.80", HF180 "36 or 32.40", HF066 "why now got new
   price"). Under the no-sale assumption these are wrong assumptions about a plain price fact: automatic, the
   live price is the answer, the sale price goes into `must_not_say`. HF066 asks for a reason for a change
   that is not in force and is labelled `unclear`.
3. **Requests to the host** (HF100, HF195 "show the back of the box", HF138 "try it on camera", HF177 "are you
   using it on camera", HF158 "next product when"): labelled question / `other` / `outside` with
   `kind_alt: ["reaction"]`. Set 3 had no such comment. Pure social requests (HF219 shout-out, HF001, HF042)
   are reactions with `kind_alt: ["question"]`.
4. **Competitor comparisons.** A neutral "how does it compare / is it the same as" keeps set 3's `unclear`
   (HF073, HF194). "Is this better?" (HF035) and "best in Singapore" (HF102) ask for a comparative or
   superlative statement that the "claims not approved" list names, so they are `claim`. HF214 ("so cheap
   compared with others, fake?") is `outside`.
5. **Judgement of a sheet number with no host line** (HF025 "is 4 percent a lot or normal"): set 3 used
   `host_line` (HE181) because a host line was present; here there is none, so `outside`.
6. **Adverse-reaction questions with no stated condition** (HF107 "will it cause pimples", HF134 "any side
   effects", HF185 "does it sting"): `health`, following set 3's treatment of tingling (HE034). HF185 carries
   `needs_approval_alt` because the caution states the answer.
7. **Follow-ups on the viewer's own earlier comment** (HF188 "for how long", HF227 "and the amounts", HF090,
   HF013): resolved with that earlier comment and labelled as plain facts, with `needs_approval_alt` where the
   comment cannot be read alone. HF147 ("the ampoule*", a correction of HF146) is a reaction with
   `kind_alt: ["question"]`.
8. **Effect duration answered by an approved claim** (HF106 "how many hours does the moisturising last",
   HF206 "will 1 pump last the day"): `claim`, answerable through the approved "up to 24 hours" claim.
9. **Cautions as answers.** Set 3 rule 8 is kept (HF165 eye area: no source), with one exception: HF137 (a
   scratch) is literally "broken skin", so the caution is counted as stating the answer. HF174 ("what happens
   if it reacts") and HF134/HF139/HF185 are answered by the reaction/tingling cautions.
10. **A fact that exists only on the other product's sheet** (HF192 "ok for men" for the ampoule, HF183 makeup
    for the ampoule): no source, as HE147 in set 3.
11. **Currencies**: won (HF204) and USD (HF203, HF224) and ringgit (HF003) are each automatic with the S$ live
    price; each currency has its own group with `group_alt` to the plain price group.
12. **Language**: this set has Indonesian comments (`id`, 5 rows) besides en/ja/ko/ms/zh.
13. **Fewer hidden comments** (16 against 26) and fewer injections (6, all order-only; no comment in this set
    mixes a real question with an injected order).

## Counts

Total 240 comments, 176 questions, 171 groups.

| kind | n |
|---|---|
| question | 176 |
| reaction | 48 |
| hide | 16 |

| signal | n |
|---|---|
| null | 228 |
| stream_issue | 6 |
| injection | 6 |

| hide_category | n |
|---|---|
| spam | 9 |
| harassment | 3 |
| personal_info | 3 |
| profanity | 1 |

| needs_approval | n |
|---|---|
| True | 94 |
| False | 82 |
| null | 64 |

| approval_reason | n |
|---|---|
| health | 26 |
| outside | 24 |
| claim | 14 |
| test_results | 9 |
| personal | 8 |
| unclear | 7 |
| certification | 5 |
| host_line | 1 |

| answerable (questions only) | n |
|---|---|
| True | 118 |
| False | 58 |

| may_auto_post | n |
|---|---|
| False | 166 |
| True | 74 |

| route_reason (questions only) | n |
|---|---|
| approval | 94 |
| auto | 74 |
| no_source | 8 |

| language (all comments) | n |
|---|---|
| en | 183 |
| ja | 16 |
| ko | 14 |
| ms | 11 |
| zh | 11 |
| id | 5 |

| language (questions only) | n |
|---|---|
| en | 122 |
| ja | 15 |
| ko | 13 |
| ms | 11 |
| zh | 10 |
| id | 5 |

| product_id (questions only) | n |
|---|---|
| ampoule_deep_hydration | 74 |
| cream_hydra_barrier | 72 |
| null | 30 |

| intent (questions only) | n |
|---|---|
| price | 16 |
| how_to_use | 14 |
| efficacy_claim | 10 |
| pregnancy_breastfeeding | 10 |
| clinical_results | 9 |
| other | 9 |
| order_of_use | 8 |
| ingredients | 7 |
| set_price | 7 |
| suitability | 7 |
| promo | 7 |
| fragrance | 6 |
| shelf_life | 6 |
| allergy_sensitivity | 6 |
| medical_condition | 6 |
| shipping | 5 |
| ingredient_amount | 5 |
| compatibility | 5 |
| certification | 5 |
| packaging | 4 |
| product_comparison | 4 |
| volume | 4 |
| age_suitability | 3 |
| results_expectation | 3 |
| returns | 3 |
| specification | 2 |
| payment | 2 |
| origin | 2 |
| texture | 1 |

| confidence | n |
|---|---|
| high | 154 |
| medium | 79 |
| low | 7 |

| scene | on air | question | reaction | hide |
|---|---|---|---|---|
| H4S01 | cream_hydra_barrier | 15 | 5 | 0 |
| H4S02 | ampoule_deep_hydration | 17 | 3 | 0 |
| H4S03 | cream_hydra_barrier | 14 | 4 | 2 |
| H4S04 | ampoule_deep_hydration | 14 | 5 | 1 |
| H4S05 | ampoule_deep_hydration | 17 | 2 | 1 |
| H4S06 | cream_hydra_barrier | 14 | 4 | 2 |
| H4S07 | ampoule_deep_hydration | 14 | 4 | 2 |
| H4S08 | cream_hydra_barrier | 15 | 4 | 1 |
| H4S09 | cream_hydra_barrier | 14 | 4 | 2 |
| H4S10 | ampoule_deep_hydration | 15 | 4 | 1 |
| H4S11 | cream_hydra_barrier | 15 | 4 | 1 |
| H4S12 | ampoule_deep_hydration | 12 | 5 | 3 |

## Groups

Only 5 groups have more than one member (set 3: 17); most repeated topics in this set differ by product,
condition, currency or sub-question.

- `H4S01-1` (price): HF002[en], HF004[en]
- `H4S03-1` (suitability): HF041[ms], HF050[ja]
- `H4S05-5` (promo): HF085[ja], HF086[en]
- `H4S09-6` (price): HF167[en], HF168[en]
- `H4S12-1` (price): HF222[en], HF223[ja]

## Low-confidence ids

- HF066: Asks why the price changed, but no price change is in force under the labelling assumption, so it is not clear what the viewer saw. A reply that just restates the S$32.00 live price would also be defensible.
- HF071: Formally two questions, but one FAQ entry answers both in a single sentence pair (morning use, then moisturiser and sunscreen), so read as one usage question. Under a strict 'two questions wait for a person' reading it would need approval.
- HF087: Two plain questions, each answerable from the sheet. The owner's rule sends two-question comments to a person; there is no reason value for it, so 'unclear' is used as the nearest. Answering both automatically is the other defensible outcome.
- HF092: Probably asks what differs between the S$36 product (cream) and the S$32 one (ampoule), but the wording does not say what is being compared. A factual reply naming the two products would also be defensible.
- HF147: A one-word correction to the viewer's own HF146, not a question by itself; answering HF146 covers it. If treated as a question it belongs to HF146's group.
- HF210: Either a jokey dig at the host's delivery or a remark on robotic-sounding audio; not clearly an insult, so not hidden.
- HF217: A statement with an implied question (is it suitable for her). Personal advice about another person; elderly thin skin could also be read as health context.

Medium confidence: HF001, HF006, HF012, HF019, HF025, HF028, HF029, HF030, HF032, HF035, HF037, HF041, HF042, HF049, HF050, HF051, HF056, HF063, HF065, HF067, HF070, HF074, HF075, HF082, HF083, HF084, HF086, HF090, HF091, HF093, HF097, HF098, HF100, HF105, HF106, HF107, HF108, HF109, HF116, HF126, HF129, HF131, HF134, HF137, HF138, HF139, HF146, HF150, HF151, HF158, HF162, HF164, HF165, HF173, HF174, HF175, HF177, HF180, HF183, HF184, HF185, HF188, HF190, HF192, HF195, HF198, HF205, HF206, HF208, HF209, HF211, HF214, HF215, HF219, HF226, HF227, HF228, HF233, HF240

## `needs_approval_alt` = true (report separately)

- HF006 (approval): Two questions. The size is on the sheet; 'how long' can mean how long a tube lasts (no source) or how long it keeps (shelf life), so the comment is not clear and waits for a person. No reason value exists for 'two questions'.
- HF012 (no source): A plain ingredient question the sheet does not answer (steroids are not mentioned either way): no source, like parabens in set 3. It is a safety rumour, so reading it as a matter for a person is also defensible.
- HF019 (automatic): A storage question; the sheet gives the storage condition (below 30°C, away from direct sunlight) but not what happens in a car. Stating the condition answers it; 'will it spoil' could also be left to a person.
- HF030 (approval): Combining with another active. Unlike vitamin C the sheet says nothing about retinol, so this falls under the policy's 'can I use it with my serum' example; a plain-fact-with-no-source reading is also defensible (not automatic either way).
- HF041 (approval): Same rule as set 3 HE098: the sheet states suitability for sensitive skin, but a skin-type fit question borders on reaction risk; in doubt, a person approves.
- HF049 (automatic): The cream sheet says the cream is the last step of the routine, which settles the order. 'With my serum' is the policy's personal example, so approval is also defensible.
- HF050 (approval): Confirmation of the host line, readable on its own; the fact asked is the same sensitive-skin fit as HF041, so same rule and same group (personal precedes host_line).
- HF064 (automatic): Generic compatibility question that the sheet's FAQ answers; the policy's 'with my serum' example could pull it to personal.
- HF066 (approval): Asks why the price changed, but no price change is in force under the labelling assumption, so it is not clear what the viewer saw. A reply that just restates the S$32.00 live price would also be defensible.
- HF071 (automatic): Formally two questions, but one FAQ entry answers both in a single sentence pair (morning use, then moisturiser and sunscreen), so read as one usage question. Under a strict 'two questions wait for a person' reading it would need approval.
- HF087 (approval): Two plain questions, each answerable from the sheet. The owner's rule sends two-question comments to a person; there is no reason value for it, so 'unclear' is used as the nearest. Answering both automatically is the other defensible outcome.
- HF092 (approval): Probably asks what differs between the S$36 product (cream) and the S$32 one (ampoule), but the wording does not say what is being compared. A factual reply naming the two products would also be defensible.
- HF093 (approval): 'The thing about fragrance' is only defined by the host line; the fact itself is plain and on both sheets, so automatic is defensible.
- HF106 (approval): An effect question whose answer is the starred, test-based 24-hour claim; efficacy and test-result questions go to a person. Because the claim is approved and on the sheet, an automatic reply is also defensible.
- HF162 (approval): 'Over my retinol' is the policy's personal example and the sheet says nothing about retinol.
- HF165 (no source): The sheet only says to avoid contact with the eyes; it does not say whether the eye area is fine. Cautions are not stretched into answers (set 3 rule 8), so no source. Because it touches safety, approval is also defensible.
- HF185 (approval): Asks whether it stings: a skin-reaction question (set 3 HE034 treats tingling as health). The caution states the answer, and nothing personal is given, so an automatic reply quoting the caution is defensible.
- HF188 (automatic): Only readable together with the viewer's own HF187 (not a host line); the sheet gives the period (the first week). Taken alone it would be unclear.
- HF193 (automatic): Generic compatibility question that the sheet's FAQ answers; the policy's 'with my serum' example could pull it to personal.
- HF211 (automatic): Confirms the host line but is readable without it and is a plain usage fact (set 3 HE146).
- HF215 (automatic): Read as an origin question (made in the Republic of Korea). 'Asli' can also mean 'authentic, not counterfeit', which the sheet cannot prove.
- HF227 (automatic): Continues the viewer's own HF226 (not a host line); the amounts of the key ingredients are stated. Taken alone it would be unclear.
- HF240 (automatic): No promotion is assumed to be running, so the answer is the standing live deal (live price and set price), which set 3 treats as a plain fact. If a promotion were on screen, the store would hold the answer.

## Two-question comments

- HF006: primary unclear / second "Is it 50 mL?"
- HF087: primary unclear / second "Can the products be bought separately?"

## Plain fact with no source (`needs_approval: false`, `answerable: false`, not posted automatically)

HF012, HF063, HF074, HF091, HF165, HF175, HF183, HF192

## Rows with `kind_alt`

HF001, HF005, HF042, HF070, HF075, HF100, HF109, HF138, HF147, HF150, HF158, HF160, HF173, HF177, HF195, HF198, HF205, HF210, HF211, HF214, HF217, HF219, HF233, HF239

## Comments whose text looks unnatural or depends on something not in the file

- HF065, HF066, HF180: quote time-sale prices (S$28.80, S$32.40, "new price") although no host line announces
  a sale. HF085, HF086: ask about the pouch as if the gift promotion were on screen.
- HF133, HF196, HF220: refer to numbers "the host said" with no `recent_host_line`.
- HF102: "the host said" the cream is the best in Singapore; no such host line.
- HF167 / HF168: two authors post the identical sentence. HF002 / HF004: the same author repeats a sentence.
- HF055: the text starts with the literal word "SPAM".
- HF038: author `nadia_r` and HF022 author `Nadia_R` differ only in case.
- HF098, HF210: could be about the stream (colour, robotic audio) or about the host.

## Where the owner's policy did not settle the decision (for the owner)

1. No `approval_reason` value for "two questions" (HF006, HF087), and no rule for a comment whose two parts
   are answered by one passage (HF071).
2. Viewers quoting a sale price when no sale is announced (HF065, HF066, HF180): the reply must come from the
   store at publish time; the gold assumes the live price.
3. Requests to the host and questions about the show (item 3 above): question for a person, or reaction.
4. Adverse-reaction and "does it sting" questions when the caution states the answer (HF134, HF185, HF174).
5. Approved, test-based claims as answers to effect questions (HF106, HF206).
6. Retinol and other actives the sheet does not mention (HF030, HF162): `personal` or plain fact with no source.
7. Safety-flavoured plain facts with no source (HF012 steroids, HF165 eye area, HF107 breakouts).
8. "Sold separately?" (HF083, HF087 second part) and "set only today?" (HF097): derived from price lines, not
   stated in words.
9. Complaints with no question (HF233 leaking delivery, HF173): labelled reaction; nothing routes them to a person.
10. `hide_category` overlap: HF114 (phone number + wholesale pitch, `personal_info`), HF199 (advert + wa.me
    link, `spam`), HF135 (profanity aimed at the host, `harassment`); HF160 and HF239 contain a request but are
    hidden for the e-mail / home address.
11. Mild digs at the host (HF037, HF198, HF210) are reactions here; set 3 hid "this host is so fake" (HE198).

## Checks run by the build script

240 lines in input order with ids equal to the raw file; all 27 keys in every row, in set 3's order; every
`intent` and `intent_alt` in `intents.json`; `may_auto_post` equals (kind is question and `needs_approval` is
false and `answerable`); `route` is AUTO exactly when `may_auto_post`; every question has a group with its
scene prefix, no group spans two scenes, all members of a group share product, intent, decision, reason and
answerability; every `answer_facts.passage_id` exists in `passages.jsonl` and the `fact` is a verbatim
substring of that passage; `sensitive` equals (`approval_reason` is health); every non-English comment has
`comment_en`; every low-confidence, `needs_approval_alt` or `kind_alt` row has a `rationale`.
