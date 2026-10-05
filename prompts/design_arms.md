# Prompt additions per design arm (D-187)

Each `## <arm family>: <agent>` section is appended to that agent's system instruction when `DESIGN_ARM` is in the
family (B: arms B and C). Arm A uses the prompt files as they are. Field names match `models/agent_io.py` (the `...B`
classes).

## B: compliance_judge

Design arm B: the server checks your output instead of judging the wording itself.
- Correction quotes: for every alert_id you put in `corrects_alert_ids`, also add `{"alert_id": ..., "quote": ...}`
  to `correction.quotes`. `quote` is the exact words of UTTERANCE that make the correction, copied verbatim, at
  least two words. The server accepts a correction only when it finds your quote in UTTERANCE.
- Test results: every violation has `qualified_result_id`. For a BRAND-TEST-QUALIFIER violation, set it to the
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
