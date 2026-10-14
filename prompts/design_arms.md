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

## F1: fact_checker

D-280 F1: an offer's terms (what it covers, who qualifies, whether it combines, where it applies) are field `promo`;
where the product is sold, in which markets or channels, and whether it is in stock are field `availability`. Use
`other` only for a statement no field fits.

## F5: fact_checker

D-280 F5: `correct_value` is always in the show's language, even when the quote is in another language: translate the
value and keep the quote verbatim as the evidence.
