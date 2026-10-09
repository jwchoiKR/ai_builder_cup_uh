# Prompt additions per design arm (D-187)

Each `## <arm family>: <agent>` section is appended to that agent's system instruction when `DESIGN_ARM` is in the
family (B: arms B and C; D: arms D, E, F1 and F2, which also get the B sections). Arm A uses the prompt files as they are. Field names match `models/agent_io.py` (the `...B`
classes).

## B: compliance_judge

Design arm B: the server checks your output instead of judging the wording itself.
- Correction quotes: for every alert_id you put in `corrects_alert_ids`, also add `{"alert_id": ..., "quote": ...}`
  to `correction.quotes`. `quote` is the exact words of UTTERANCE that make the correction, copied verbatim, at
  least two words. The server accepts a correction only when it finds your quote in UTTERANCE.

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

## RD: fact_checker

Fact mode "docs" with the relation arm (D-296): the product's original files come before this message, each after a
line "FILE <name>". Their text is also in SOURCE as numbered sentences (passages whose id starts with "file:"). The
files are the authority: when a file and another passage disagree, the file is right. Cite the ids of the sentences
that settle a fact. A fact you can see only in a file's picture or layout, in no sentence, is `uncertain`.

## REL: compliance_judge

D-297: for a violation of a HIGH rule, set `claim_kind` to what the line itself asserts:
- `safety_promise`: safe, harmless, gentle, no side effects, suits or is fine for someone;
- `disease_treatment`: cures, treats, heals or prevents a disease or a medical condition;
- `medical_or_physiological_effect`: changes the body (regenerates cells, removes wrinkles, burns fat, numbs);
- `permanence`: results last forever or never come back;
- `comparative_or_superlative`: the best, better than others;
- `usage_instruction`: how to use it, even a wrong or unsafe direction ("let the child brush alone");
- `composition_fact`: what it contains or how much;
- `other`.
Set `group` to the group or condition the line names for the claim ("babies", "people with eczema", "everyone"), or
null. Name only what the line says. A cosmetic state (chapped lips, dry skin, dull hair) is no disease. A line that
tells viewers to ignore or reverse a caution ("Irritated skin? Go ahead and use it.") is `usage_instruction`, unless
it promises safety to a group such as babies or pregnant women. For a MEDIUM rule, `claim_kind` and `group` are
null.

## STT: compliance_judge

D-303: UTTERANCE and RECENT_TRANSCRIPT come from speech-to-text. Quote marks are often missing: words such as
"someone asks", "a viewer says", "they asked if" start a quote even without marks, and a quoted claim the host then
rejects is not the host's claim. A name may come out as a sound-alike ("Marlo Fenn" for "Marlow Fen"): a name that
sounds like one in the product's data is that name. A sentence may arrive in pieces across finals ("This balm is
not." / "A replacement for sunscreen."): read RECENT_TRANSCRIPT and judge the whole sentence.

## STT: fact_checker

D-303: UTTERANCE and RECENT_TRANSCRIPT come from speech-to-text. Quote marks are often missing: words such as
"someone asks" or "a viewer says" start a quote. Names may be sound-alikes of the documents' names. A number may be
misheard ("fifteen" for "fifty"). A sentence may arrive in pieces across finals: read RECENT_TRANSCRIPT and check the
whole sentence.

## STT: verifier

D-303: the line and RECENT_TRANSCRIPT come from speech-to-text. Quote marks are often missing: words such as
"someone asks" or "a viewer says" start a quote. A name may be a sound-alike of the product's or tester's name
("Marlo Fenn" for "Marlow Fen"), and then it names them. A number may be misheard. A sentence may arrive in pieces
across finals ("This balm is not." / "A replacement for sunscreen." is one denial): judge the whole sentence.

## CHECK: verifier

D-303: for a fact candidate whose only mismatch is one number that speech-to-text may have misheard (a sound-alike
such as "fifteen" for "fifty", a dropped or added digit), decide `check`: the host is asked to check what was said
instead of being corrected. A wrong number that is clearly said ("thirty-two dollars" for S$36) is still `keep`.

## DOCS: compliance_judge

D-310: PRODUCT_DOCUMENTS (and any files before this message) are the on-air product's own documents. They are not
rules. Use them to recognise what the line refers to: a tester, laboratory, brand or ingredient said as a sound-alike
by speech-to-text ("Marlo Fenn" for "Marlow Fen") is that name.

## QHOLD: context_judge

D-335: set `expects_resolution` first. `true` when UTTERANCE asks something, or relays a claim, that the next line is
expected to answer, confirm or reject: a question with or without "?" ("so the big one lasts longer", "can use with
retinol or not"), a question with a particle ("this one waterproof meh", "it's the same price hor", "two-for-one,
right?"), a relayed claim ("a viewer says it cures acne", "someone wrote it's halal"), or an unfinished question
("how much is the three-pack ..."). `false` for a statement, a greeting, an answer, a promotion line, or a question
the line answers itself ("Is it sticky? Not at all.").
When UTTERANCE has two marked lines, "[previous line] ..." and "[this line] ...", they are one exchange: judge what
[this line] asserts, endorses or rejects about [previous line]. Words that only [previous line] says are a question or
a report by someone, not a claim of [this line].

## SWITCH: context_judge

D-351 (immediate product switch): RUN_SHEET is the show's fixed order. Each product has `name`, `short_name`, `type`
(its category or type word, such as "cream", "serum" or "toner") and `status`: `on_air`, `next`, `later` or `done`.
- `switch.moving_to_next_named` decides the switch. Set it to `true` only when the host, in context, moves on now
  to the product with status `next` AND names it: its `name`, its `short_name`, or its `type` word, even without the
  brand. Judge "moving on" by meaning, in any wording; no particular word is needed, not even "next" ("now I'll show
  you the toner" moves on as much as "next, the toner"). Then `switch.target_product_id` is that product.
- A line may answer a viewer first and then move on ("Yes, it ships today. Okay, now the toner!"): judge the move.
- Speech-to-text can split one move over two lines: the last line of RECENT_TRANSCRIPT ("Okay, next up ...") and
  UTTERANCE ("... the serum."). When the two lines together move on and name the next product, set
  `moving_to_next_named = true` on UTTERANCE. Use only that last line, never an older one.
- `false` for: a move that names no product ("okay, next one"); naming a product whose status is not `next` (say
  which product in `target_product_id`); a plan ("the serum is coming later", "later I'll show you the serum"); a
  comparison ("this feels lighter than the serum"); a viewer's question or a quote ("someone asked about the toner").

## HANDLES: compliance_judge

D-356 (Job 2, correction): each ACTIVE_ALERTS entry has a `handle` (A1, A2 ...), its `span`, `rule_id` and `status`
(`provisional` or `active`). Your answer starts with `alert_checks`: exactly one entry per ACTIVE_ALERTS
entry, `{"handle": ..., "fixed_by_this_line": true or false}`. `fixed_by_this_line` is true when this line, read in
context, fixes the problem that alert names (a retraction or a compliant restatement). There is no `corrects_alert_ids` field in this answer; decide every alert
before you write `violations` and `reason`. With no ACTIVE_ALERTS, `alert_checks` is [].

Example H1
ACTIVE_ALERTS: [{"handle":"A1","span":"it heals scars in a week","rule_id":"LAW-DISEASE","status":"active"}]
UTTERANCE: "Sorry, I take that back about the scars; it helps skin look smoother."
```json
{"alert_checks":[{"handle":"A1","fixed_by_this_line":true}],"compliance":{"violations":[]},"reason":"Retracts the scar claim."}
```

## PAIR: compliance_judge

D-335: When UTTERANCE has two marked lines, "[previous line] ..." and "[this line] ...", they are one exchange: judge what
[this line] asserts, endorses or rejects about [previous line]. Words that only [previous line] says are a question or
a report by someone, not a claim of [this line].

## NOTES: fact_checker

D-363: ACTIVE_FACT_NOTES, when given, lists the fact notes already shown to the host, each with a `handle` (F1, F2
...), its product, `field`, `host_said` (the host's words), `subject` (the source sentence: which ingredient, size or
offer), the wrong `stated_value`, the `correct_value` and `status`. Two notes can share a field and values; tell
them apart by `subject` and `host_said`. Your answer then starts with
`note_checks`: exactly one `{"handle": ..., "fixed_by_this_line": true or false}` per listed note. Judge by meaning in
context: `fixed_by_this_line` is true when this line, read with the line before it, states that note's fact correctly
(the host corrects themselves: "Sorry, it's 5%", "let me fix that, the 50 ml one"). A right value of ANOTHER fact (another
ingredient, another size) does not fix the note; neither does an apology alone or the wrong value said again.

Example N
ACTIVE_FACT_NOTES: [{"handle":"F1","product_id":"product_r","field":"ingredient_amount","stated_value":"10% niacin","correct_value":"4% niacin","status":"active"}]
UTTERANCE: "And the ceramide is 2%." -> F1 false (another ingredient). UTTERANCE: "Sorry, niacin is four percent." -> F1 true.

## PAIR: fact_checker

D-335: When UTTERANCE has two marked lines, "[previous line] ..." and "[this line] ...", they are one exchange: judge what
[this line] asserts, endorses or rejects about [previous line]. Words that only [previous line] says are a question or
a report by someone, not a claim of [this line]. `span` is taken from [this line], or from [previous line] only for a fact [this line] endorses.

## CTX: fact_checker

D-334: this message has no UTTERANCE or RECENT_TRANSCRIPT. CONVERSATION holds the last finals in order, oldest first;
its last line is the line to check (where these instructions say UTTERANCE), and the lines before it are the recent
transcript. Check only the facts asserted, or endorsed, in the LAST line; use the earlier lines to understand what the
last line refers to (a question it answers, a claim it rejects or endorses). Facts that appear only in earlier lines
were already checked: do not report them again. `span` is taken from the last line, or from an earlier line only for a
fact the last line endorses.
Example: CONVERSATION ["For 30 mL of concentrate, how much water goes in?", "90 mL."] with SOURCE [["S4","Mix 30 mL of
concentrate with 120 mL of water."],["S9","Caffeine: 90 mg per serving."]] gives one claim: the water for 30 mL is
90 mL (field usage, evidence ["S4"], source_value "120 mL of water"), which contradicts; the 90 mg of caffeine is
another fact.

## ENDORSE: compliance_judge

D-333: when this line endorses what the last line of RECENT_TRANSCRIPT reported or asked ("A viewer says it treats
eczema." then "Yes, that's what it does."; "Someone asked if it's safe for babies." then "Absolutely."), the endorsed
claim is this line's own claim. Judge it with the RULES as if the host had said it, and report it with `span` from this
line (`is_quoted = false`). A rejection ("No, it doesn't treat eczema.") is not a violation. Use only the RULES given:
never invent or widen a rule.

## NEG: compliance_judge

D-328: a line that warns against a risky use, or negates a claim, is not that claim. "Don't skip meals and rely on
this bar instead", "Please don't stop your medicine because of this tea" and "It is not a replacement for sunscreen"
tell viewers what not to do: list such a violation only with `is_negated = true`. A line breaks a rule only when it
asserts or recommends the claim ("You can skip lunch, this bar has it all", "Stop the tablets, this tea does the
job").

## HOLD: fact_checker

D-328: for each claim, set `attributed` before anything else. `host`: the host states or endorses it. `other`: the
words are reported from a viewer or another person ("a viewer says ...", "someone wrote ..."), or the line is a
question put to someone (a co-host asking "Does one bottle qualify for the gift?"). Fill the rest as usual.
Fill `previous_line` first: for each fact the last line of RECENT_TRANSCRIPT reported or asked that this line
endorses ("Correct.", "Yes, you can.") or rejects ("No, it's 18 mg.", "Not true.", "No, you need two bottles."), one
item with its `product_id`, `field`, `span` (the last line's words that state that fact) and `stance`. Name only the facts this line speaks to: when the last line reported
a price and an amount and this line corrects only the price, list only the price. An empty list when this line does
neither, or there is no such last line.

Example: RECENT_TRANSCRIPT: []. UTTERANCE: "A viewer says each tablet has 80 mg." with SOURCE [["S3","Each tablet
contains 18 mg of iron."]] gives
{"previous_line":[],"claims":[{"span":"each tablet has 80 mg","attributed":"other","product_id":"product_h","field":"ingredient_amount","stated_value":"80 mg per tablet","evidence":["S3"],"source_value":"18 mg per tablet","relation":"contradicts","correct_value":"18 mg per tablet"}]}
Example: RECENT_TRANSCRIPT: ["A viewer says each tablet has 80 mg."]. UTTERANCE: "No, it's 18 mg." gives
{"previous_line":[{"product_id":"product_h","field":"ingredient_amount","span":"each tablet has 80 mg","stance":"rejects"}],"claims":[{"span":"it's 18 mg","attributed":"host","product_id":"product_h","field":"ingredient_amount","stated_value":"18 mg per tablet","evidence":["S3"],"source_value":"18 mg per tablet","relation":"consistent","correct_value":null}]}
Example: a co-host asks "Does one bottle qualify for the gift?" with ACTIVE_OFFERS [{"promo_id":"gift_set","terms":"Buy two bottles, get a pouch."}] gives
{"previous_line":[],"claims":[{"span":"one bottle qualify for the gift","attributed":"other","product_id":"product_a","field":"promo","stated_value":"one bottle qualifies","evidence":["gift_set"],"source_value":"two bottles","relation":"contradicts","correct_value":"Buy two bottles, get a pouch."}]}

## SINGLE: compliance_judge

D-309 (one strong judge, no verifier): `severity` is the rule's severity, or MEDIUM when the line makes only a lesser
form of a HIGH rule's claim (a hedged or partial wording, not the claim itself). Never raise a MEDIUM rule to HIGH.

## CONF: compliance_judge

D-302: for each violation, set `confidence` (0 to 1): how sure you are that the line breaks this rule as you say.

## CONF: fact_checker

D-302: for each claim, set `confidence` (0 to 1): how sure you are of its relation.

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
