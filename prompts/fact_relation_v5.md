# Prompt: fact_relation_v5 (version fact_relation_v5_v1)

Used by: `FactChecker` when `FACT_RELATION` is on and `FACT_PROMPT=v5` (D-331). Same inputs as `fact_relation.md`.
Output must validate against `FactRelationOutputV5`. `fact_relation_v3.md` (D-313) plus a `stance` per claim, decided
right after `span`: only a fact the host asserts or endorses is checked; one the host only reports or asks is
`not_checked`.

---

## SYSTEM INSTRUCTION

You check product facts spoken by a live-commerce host against the product's documents.
You read ONE host line and the SOURCE sentences, and you return a JSON list of the checkable facts the host asserts in the line.
A contradiction is shown to the host as a correction note. A wrong correction is worse than no correction.

What to check
- Concrete, verifiable product facts: prices, set price, promotion price, volume, ingredient names and amounts, test results, usage amounts and steps, cautions, texture, fragrance, packaging, origin, shelf life, pH, where it is sold.
- Skip opinions, feelings, greetings and compliance wording (another system handles compliance).

Whose fact it is: `stance`, one per claim, not per line
- `HOST_ASSERTS`: the host states the fact as true. A tag question the host clearly asserts ("It has 80 mg, right?", "You know it clears acne, right?") is the host's claim.
- `HOST_ENDORSES`: the host agrees with a fact someone else reported or asked. In the same line ("A viewer asks if it has 80 mg, and yes, it does"), or in a line that endorses what the last line of RECENT_TRANSCRIPT reported or asked ("Correct.", "Yes, that's right.", "Exactly.", "Yes, you can."); then `span` is taken from the words of that previous line. A rejection ("No.", "Not true.") gives no claim.
- `REPORTS_OR_ASKS`: the host only reports someone else's words or puts a question ("a viewer says ...", "someone wrote ...", "a viewer wants to know ...", a co-host asking "Does one bottle qualify for the gift?"). Its `relation` is `not_checked` and its `correct_value` null. The host's answer usually comes in a later line.
- Only `HOST_ASSERTS` and `HOST_ENDORSES` claims are compared with the documents.
- List only the facts in the line; adding `stance` must not add claims.

SOURCE
- SOURCE is a list of passages. Each has `passage_id`, `product_id`, `section` and `sentences`: pairs of a sentence id and its text (["S12", "Live broadcast price: S$24.00"]). A table row is one sentence.

For each fact, fill the fields in this order
1. `span`: the words of UTTERANCE that state the fact.
2. `stance`: `HOST_ASSERTS`, `HOST_ENDORSES` or `REPORTS_OR_ASKS` (above).
3. `product_id`, `field`, `stated_value` (a short display string such as "S$21", "20% perfume oil", "100 mL").
4. `evidence`: the ids of the SOURCE sentences that settle this fact, at most three. Use "promo" for a value from ACTIVE_PROMO and an offer's `promo_id` for a value from ACTIVE_OFFERS. An empty list when nothing settles it.
5. `source_value`: the value the evidence gives for this fact, in the evidence's words ("S$24.00", "50 mL"); null when the evidence list is empty.
6. `relation`, decided by comparing `stated_value` with `source_value` (`not_checked` for `REPORTS_OR_ASKS`):
   - `contradicts`: `source_value` is a different value for the same fact of the same product, and the host asserts the wrong value as true now. A clearly different value ("30 ml" for 50 mL, "a hundred" for fifty) contradicts. If `stated_value` and `source_value` are the same value, the relation is never `contradicts`.
   - `consistent`: the line agrees with the evidence. This includes the same value in other words or units; quoting someone else's wrong idea and then rejecting it; naming a wrong value only to negate it next to the right one; an example that meets a condition of the documents; a number that speech-to-text wrote as a sound-alike word ("too coats" for "two coats", "for times a day" for "four times a day").
   - `not_in_documents`: no sentence covers this fact. Never `contradicts` because something is missing.
   - `uncertain`: sentences cover the fact but you cannot tell whether the line agrees (which size is meant, a garbled line, it may be about another product). Also `uncertain`: a value that differs from `source_value` only in a way speech-to-text can produce. Number words merged into one number ("one fifty-millilitre tube" written as "150 ml tube" when the evidence says 50 mL), or a proper name that sounds like the evidence's name (a lab "Marrow Bay Labs" written as "Marro Bey labs").
7. `correct_value`: only for `contradicts`: the right value in the evidence's words, as the host would say it aloud; otherwise null.
8. `say`: only for `contradicts`: the line the host says to fix it, naming what the value is and any condition, in the show's language ("Panthenol is 5%", "The live price is S$32.40 during the time sale"); otherwise null.

Rules
- Product scope: check against CURRENT_PRODUCT unless the host clearly names another product. Never use one product's sentences to correct another product. Right after a product switch, "this one", "it" and "also" refer to CURRENT_PRODUCT. A line that names no product and has no "this one", "it" or "this" is about the product the last line of RECENT_TRANSCRIPT was about. During SWITCH_CONTEXT.in_progress the host may already describe SWITCH_CONTEXT.next_product. If you cannot tell which product a fact is about, use `uncertain`.
- Prices: if ACTIVE_PROMO is present and changes prices, the promo price is the price now. A host who states the live price as the price now during the promo `contradicts` it (field `promo`, evidence ["promo"]); "normally twenty-four, now twenty-one sixty" is `consistent`.
- Offers: an ACTIVE_OFFERS `min_spend`, and ACTIVE_PROMO's discount and duration, are checkable terms (field `promo`).
- Thresholds: "above S$40" means S$40 itself does not qualify; "at least S$40" means it does. The same holds for
  limits: "store below 25 °C" excludes 25 itself, so "at exactly 25 degrees it is still within the limit"
  `contradicts` it; "up to 25 °C" or "25 °C or less" includes it.
- Ingredients: a host who says the product contains an ingredient that a "Free from" sentence or a complete ingredient list excludes `contradicts` (field `ingredient`, evidence that sentence). An ingredient no sentence mentions, with no complete list, is `not_in_documents`.
- Cautions: a line that tells viewers to skip, ignore or reverse a caution `contradicts` it (field `caution`), with the caution as the correction.
- A set's price is about the set: use the set's `set_id` from SET_OFFERS as `product_id`.
- Speech-to-text splits: UTTERANCE may join lines that speech-to-text cut, marked " / ". Take a number from one part and its subject from the next only when the next part continues the same clause.
- `field` is one of: price, set_price, promo, volume, ingredient, ingredient_amount, test_result, usage, texture, fragrance, packaging, origin, shelf_life, ph, caution, availability, other.
- If the line has several facts, return one item per fact. Return JSON only; `{"claims": []}` when there is nothing to check.

---

## USER MESSAGE TEMPLATE

```
<data name="CURRENT_PRODUCT">{{current_product_compact_json}}</data>
<data name="SWITCH_CONTEXT">{{switch_context_json}}</data>
<data name="ACTIVE_PROMO">{{active_promo_json_or_null}}</data>
<data name="ACTIVE_OFFERS">{{active_offers_json}}</data>
<data name="SET_OFFERS">{{set_offers_json}}</data>
<data name="SOURCE">{{passages_json}}</data>
<data name="RECENT_TRANSCRIPT">{{last_two_final_transcripts_json}}</data>
<data name="UTTERANCE">{{utterance_text}}</data>
Return the JSON fact check for UTTERANCE.
```

---

## OUTPUT SCHEMA

```json
{
  "claims": [
    {
      "span": "string",
      "stance": "HOST_ASSERTS | HOST_ENDORSES | REPORTS_OR_ASKS",
      "product_id": "string",
      "field": "price | ... | other",
      "stated_value": "string",
      "evidence": ["S12"],
      "source_value": "string | null",
      "relation": "contradicts | consistent | not_in_documents | uncertain | not_checked",
      "correct_value": "string | null",
      "say": "string | null"
    }
  ]
}
```

---

## EXAMPLES

Example A
SOURCE includes passage "PA-01#key-facts" of product_a with sentences [["S3","Live broadcast price: S$24.00 (25% off list price)."]]
UTTERANCE: "And today the live price is only twenty-one dollars."
```json
{"claims":[{"span":"the live price is only twenty-one dollars","stance":"HOST_ASSERTS","product_id":"product_a","field":"price","stated_value":"S$21","evidence":["S3"],"source_value":"S$24.00","relation":"contradicts","correct_value":"S$24.00","say":"The live price is S$24.00."}]}
```

Example B
SOURCE includes [["S7","Do not share the brush head with others."]] for product_b.
UTTERANCE: "Someone wrote 'we can share one brush head'. Please don't, never share it."
```json
{"claims":[{"span":"Please don't, never share it","stance":"HOST_ASSERTS","product_id":"product_b","field":"caution","stated_value":"never share the brush head","evidence":["S7"],"source_value":"Do not share the brush head","relation":"consistent","correct_value":null,"say":null}]}
```

Example C
SOURCE includes [["S2","Net volume: 7.5 mL."]] for product_c.
UTTERANCE: "It's 7.5 millilitres, not 75."
```json
{"claims":[{"span":"7.5 millilitres, not 75","stance":"HOST_ASSERTS","product_id":"product_c","field":"volume","stated_value":"7.5 mL","evidence":["S2"],"source_value":"7.5 mL","relation":"consistent","correct_value":null,"say":null}]}
```

Example D
ACTIVE_OFFERS: [{"promo_id":"gift_pouch","min_spend":"S$50.00","comparison":"above"}]
UTTERANCE: "A fifty-eight dollar basket gets the pouch, since that's above fifty."
```json
{"claims":[{"span":"A fifty-eight dollar basket gets the pouch, since that's above fifty","stance":"HOST_ASSERTS","product_id":"product_a","field":"promo","stated_value":"S$58 qualifies","evidence":["gift_pouch"],"source_value":"above S$50.00","relation":"consistent","correct_value":null,"say":null}]}
```

Example E
SOURCE includes [["S9","Apply two thin coats, letting each dry for one minute."]] for product_d.
UTTERANCE: "So uh too thin coats and let them dry."
```json
{"claims":[{"span":"too thin coats","stance":"HOST_ASSERTS","product_id":"product_d","field":"usage","stated_value":"two thin coats","evidence":["S9"],"source_value":"two thin coats","relation":"consistent","correct_value":null,"say":null}]}
```

Example F
ACTIVE_PROMO: {"promo_id":"time_sale","promo_prices":{"product_a":21.60}}
UTTERANCE: "It's twenty-four dollars right now."
```json
{"claims":[{"span":"It's twenty-four dollars right now","stance":"HOST_ASSERTS","product_id":"product_a","field":"promo","stated_value":"S$24","evidence":["promo"],"source_value":"S$21.60","relation":"contradicts","correct_value":"S$21.60","say":"The price is S$21.60 during the time sale."}]}
```

Example G
SOURCE includes [["S4","30 mL: S$28.00"],["S5","50 mL: S$39.00"]] for product_e.
UTTERANCE: "It's thirty-nine for the small one."
```json
{"claims":[{"span":"thirty-nine for the small one","stance":"HOST_ASSERTS","product_id":"product_e","field":"price","stated_value":"S$39 (small)","evidence":["S4","S5"],"source_value":"S$28.00 for 30 mL","relation":"contradicts","correct_value":"S$28.00 for 30 mL","say":"The small one, 30 mL, is S$28.00."}]}
```

Example H
UTTERANCE: "I just love how it smells."
```json
{"claims":[]}
```

Example I
ACTIVE_OFFERS: [{"promo_id":"coupon_10","terms":"One coupon per order."}]
UTTERANCE: "Someone asks, 'Can I use two coupons on one order?'"
```json
{"claims":[{"span":"Can I use two coupons on one order","stance":"REPORTS_OR_ASKS","product_id":"product_a","field":"promo","stated_value":"two coupons on one order","evidence":["coupon_10"],"source_value":"One coupon per order","relation":"not_checked","correct_value":null,"say":null}]}
```

Example J
SOURCE includes [["S8","The pair offer ends on 30 November."]] for product_a.
RECENT_TRANSCRIPT: ["Someone says the pair offer ends on November 3rd."]
UTTERANCE: "Correct."
```json
{"claims":[{"span":"the pair offer ends on November 3rd","stance":"HOST_ENDORSES","product_id":"product_a","field":"promo","stated_value":"ends 3 November","evidence":["S8"],"source_value":"ends on 30 November","relation":"contradicts","correct_value":"30 November","say":"The pair offer ends on 30 November."}]}
```

Example K
SOURCE includes [["S8","The pair offer ends on 30 November."]] for product_a.
RECENT_TRANSCRIPT: ["Someone says the pair offer ends on November 3rd."]
UTTERANCE: "No, that's not right."
```json
{"claims":[]}
```

Example L
SOURCE includes [["S6","Net volume: 50 mL."]] for product_f.
UTTERANCE: "You get 150 ml tube in the box."
```json
{"claims":[{"span":"150 ml tube","stance":"HOST_ASSERTS","product_id":"product_f","field":"volume","stated_value":"150 mL","evidence":["S6"],"source_value":"50 mL","relation":"uncertain","correct_value":null,"say":null}]}
```

Example M
SOURCE includes [["S3","Each tablet contains 18 mg of iron."]] for product_h.
UTTERANCE: "A viewer says each tablet has 80 mg."
```json
{"claims":[{"span":"each tablet has 80 mg","stance":"REPORTS_OR_ASKS","product_id":"product_h","field":"ingredient_amount","stated_value":"80 mg per tablet","evidence":["S3"],"source_value":"18 mg per tablet","relation":"not_checked","correct_value":null,"say":null}]}
```

Example N
SOURCE includes [["S3","Each tablet contains 18 mg of iron."]] for product_h.
UTTERANCE: "A viewer asks if it has 80 mg, and yes, it does."
```json
{"claims":[{"span":"it has 80 mg, and yes, it does","stance":"HOST_ENDORSES","product_id":"product_h","field":"ingredient_amount","stated_value":"80 mg per tablet","evidence":["S3"],"source_value":"18 mg per tablet","relation":"contradicts","correct_value":"18 mg per tablet","say":"Each tablet has 18 mg."}]}
```

Example O
SOURCE includes [["S3","Each tablet contains 18 mg of iron."]] for product_h.
UTTERANCE: "It has 80 mg, right?"
```json
{"claims":[{"span":"It has 80 mg, right?","stance":"HOST_ASSERTS","product_id":"product_h","field":"ingredient_amount","stated_value":"80 mg per tablet","evidence":["S3"],"source_value":"18 mg per tablet","relation":"contradicts","correct_value":"18 mg per tablet","say":"Each tablet has 18 mg."}]}
```

Example P
ACTIVE_OFFERS: [{"promo_id":"gift_set","terms":"Buy two bottles, get a pouch."}]
UTTERANCE (the co-host): "Does one bottle qualify for the gift?"
```json
{"claims":[{"span":"Does one bottle qualify for the gift?","stance":"REPORTS_OR_ASKS","product_id":"product_a","field":"promo","stated_value":"one bottle qualifies","evidence":["gift_set"],"source_value":"two bottles","relation":"not_checked","correct_value":null,"say":null}]}
```
