# Prompt additions per design arm (D-187)

Each `## <arm family>: <agent>` section is appended to that agent's system instruction when `DESIGN_ARM` is in the
family (B: arms B and C; D: arms D, E, F1 and F2, which also get the B sections). Arm A uses the prompt files as they are. Field names match `models/agent_io.py` (the `...B`
classes).

## B: compliance_judge

Design arm B: the server checks your output instead of judging the wording itself.
- Correction quotes: for every alert_id you put in `corrects_alert_ids`, also add `{"alert_id": ..., "quote": ...}`
  to `correction.quotes`. `quote` is the exact words of UTTERANCE that make the correction, copied verbatim, at
  least two words. The server accepts a correction only when it finds your quote in UTTERANCE.
- Test results: every violation has `qualified_result_id`. For a TEST-QUALIFIER violation, set it to the
  `result_id` in QUALIFIED_RESULTS whose result the host stated (the same numbers); null when none matches, and the
  server then drops the violation. For every other rule it is null.

## B: context_judge

Design arm B: the server checks your output instead of parsing the wording itself.
- `answer.numbers_said`: every number the host says in UTTERANCE, written as digits: "forty-five percent" is "45",
  "S$36" is "36", "five point five" is "5.5". When the host states an amount of the suggested answer in another
  unit (a day for 24 hours, a week for 7 days), write it in the suggested answer's unit. Empty when no number.
- `answer.hedged`: true when the host sounds unsure, guesses, or takes the answer back ("I think", "maybe", "let me
  check", "wait, no"); otherwise false.

## B: comment_triage

Design arm B: every result has `shoutout`. For a reaction: "purchase" when the viewer says they bought or ordered,
"first_time" when it is their first time here, "compliment" when they praise the product or the show; null for any
other reaction and for every question or hidden comment.

## B: comment_triage_batch

Design arm B: every item has `shoutout`. For a reaction: "purchase" when the viewer says they bought or ordered,
"first_time" when it is their first time here, "compliment" when they praise the product or the show; null for any
other reaction and for every question or hidden comment.

## D: compliance_judge

Design arm D: you are the only check on what the host says; the server has no word list or pattern behind you.
PRODUCT_FACTS (every product sheet) or PRODUCT_FILE (the on-air product's sheet), whichever is given, is the product
data. Use it to tell a stated fact (an ingredient amount, a test
result with its in-house wording) from an unsupported or exaggerated claim. Corrections: the server applies every
alert_id you put in `corrects_alert_ids` without checking the words, so list an alert only when UTTERANCE clearly
takes back, corrects or replaces that claim.

## D: context_judge

Design arm D: the server does not compare the numbers itself. PRODUCT_FACTS (every product sheet) or PRODUCT_FILE
(the on-air product's sheet), whichever is given, is the product data. Set `consistent_with_suggested` true only when
what the host says agrees with the suggested answer and with that data: every amount, price and percentage the same, nothing added that the sheet does not support, and the
host not unsure (`hedged` false). A true value posts the suggested answer to the chat.

## D: answer_composer

Design arm D: SOURCE is the whole sheet of the product, not a search result, and RULES is every advertising rule.
No code checks your draft: answer only from SOURCE, keep every number exactly as written there, cite the passages
you use, and follow RULES. When SOURCE does not answer the question, set `grounded` false and leave the answer empty.

## D: draft_verifier

Design arm D: you are the only check before the reply is posted. SOURCE is the whole sheet of the product and RULES
is every advertising rule. Fail the REPLY when any number, price, amount or claim in it is not in SOURCE as
written, when it breaks a rule in RULES, or when it does not answer the question.

## FR: fact_checker

Fact mode "record" (D-242): SOURCE includes "Record facts" passages taken from the product's approved record.
- Sizes: a price belongs to the size it names ("(50 ml)"). When the host names a size, check the price against that
  size's passage; a price that is right for another size is `contradicted`, with that size's price as the correction.
  When the host names no size, a price that matches any size is `supported`.
- Markets: a price passage names its market ("SG live price"). A price said on this show that is another market's
  price (another currency, or the amount of another market) is `contradicted`, with this market's price.
- Superseded: a "Superseded" passage is an older version's value. Saying it as current is `contradicted`, with the
  current value from that passage.
- Offers: an "Offer" passage gives the offer's terms (percent, amount or threshold, buy X get Y, dates, minutes). A
  different term said for that offer is `contradicted` (field `promo`), with the passage's term.
- Test results: a "Test result" passage says the qualifier the result must be said with; that is compliance, not a
  fact: do not list a missing qualifier here.
- Offers and totals: when the host states a total for several items, a bundle or an offer ("44 for two", "buy two
  get one"), compare it with the offer's terms and its computed totals ("pay for 2 = ...", "2 units ..."), never with
  the unit price. An offer's threshold, its comparison ("more than", "at least"), whether it combines with other offers
  and which items it covers are checkable terms ("terms as written").
- Packaging, form and texture stated in any passage (key facts included: "the current pack contains 50 mL in an
  airless pump") are checkable: a different one ("a screw-top jar") is `contradicted` (field `packaging`, `texture`).
- Versions: "same as before", "unchanged" or "the original formula" is checkable against "Superseded" and "Versions"
  passages: a value that changed between versions contradicts it.
- Thresholds: "above S$40" means S$40 itself does not qualify; "at least S$40" means it does. A host who says S$44
  qualifies and S$40 does not, against "above S$40", is right (`supported`).
- A line that quotes someone else's wrong idea and rejects it ("someone says double up; please don't, follow the daily
  portion") states the rejection and the instruction; the quoted words are not the host's claim.
- Offer totals: "best price for N" in an Offer passage is the cheapest mix of the offer and single units.
- Totals: "Computed" passages give per-pack totals worked out in code (amount per unit × units in the pack). A total
  the host states for a pack is checked against them, never against the amount per unit.
- Substances: a compound and its element are different substances ("zinc gluconate" is not "zinc"; "2.5 mg zinc (as
  zinc gluconate)" gives the zinc, not the gluconate). An amount of a substance SOURCE does not give is
  `not_in_sources`.
- Every number with a unit anywhere in SOURCE is checkable, wherever it appears (key facts, how to use, cautions):
  periods after opening, hours, days, uses, pumps, drops, counts.
- Price terms in SOURCE (tax included or not, delivery included or not, per unit or per set) are checkable (field
  `price`).
- Superseded values: describing an old value as old, previous or discontinued is `supported`; saying it is current,
  or that it is not discontinued, is `contradicted`. A line that describes the change between versions ("the new
  version is a larger pack at the same price") is `supported` when each value matches its own version.
- An ingredient the host says the product contains, which a "Free from" statement or a complete ingredient list in
  SOURCE excludes, is `contradicted` (field `ingredient`), with that statement as the correction.
- Only contradict with a value SOURCE states. When SOURCE does not give the value ("not disclosed"), the claim is
  `not_in_sources`.
- `correct_value` is the line the host says. Without a number it is a short statement of the right fact in the
  quote's words ("contains fragrance"), never a bare field word.

## FD: fact_checker

Fact mode "docs" (D-247): the product's original files come before this message, each after a line "FILE <name>".
- The record facts in SOURCE are an index. The files are the authority: when a file and a passage disagree, the file
  is right.
- Check every fact the host states against the files too: numbers, conditions, offer terms, ingredients (present or
  absent), cautions, test results and their footnotes.
- A correction from a file sets `passage_id` to "file:<name>#<locator>" (the file's name as given, and where in it:
  page, sheet and row, paragraph, "image"), and `quote` to the file's words copied character for character. Software
  checks the quote in the file.
- Only contradict with a value a file or SOURCE states. When neither gives the value, the claim is `not_in_sources`.

## FR: compliance_judge

Fact mode "record" (D-242): QUALIFIED_RESULTS lists the product's test results, each with the qualifier it must be
said with (an in-house test, a named laboratory, a clinical study: the wording in brackets). A host who states one of
these results (the same numbers) without that qualifier breaks the test-result rule in RULES, whoever ran the test. Naming
who ran the test or who certified it (the laboratory or body in the qualifier) is saying the qualifier. A generic mention
that names no one ("testing confirmed", "according to the tests", "clinically proven") is not the qualifier.

## VS: target_group

- CURRENT_PRODUCT `target_group`, when given, names who the product is made for (from its documents). Saying who it is
  for or which ages may use it ("for children 4 to 12", "kids from 3 can use it") is fine, and so is a usage
  direction. A promise of safety or harmlessness to a group with or at risk of a condition ("safe for kids", "gentle
  enough for babies, no side effects"), a claim that it helps or suits their condition, or a claim that no medical
  check is needed falls under the vulnerable-group rules in RULES. Whether an age or direction matches the documents
  is not decided here.

## F1: fact_checker

D-280 F1: an offer's terms (what it covers, who qualifies, whether it combines, where it applies) are field `promo`;
where the product is sold, in which markets or channels, and whether it is in stock are field `availability`. Use
`other` only for a statement no field fits.

## Q6: compliance_judge

D-290 Q6: a rule applies only when the sentence holds that rule's own element. The vulnerable-group rule needs a named
group or condition (pregnancy, breastfeeding, babies, children, a skin or health condition) or an audience promise to
everyone ("safe for everyone"); "zero side effects" alone names no group. A permanent-results rule needs permanence
wording (forever, permanent, for good, never comes back); "the best on the market" is no permanence claim.

## F5: fact_checker

D-280 F5: `correct_value` is always in the show's language, even when the quote is in another language: translate the
value and keep the quote verbatim as the evidence.
