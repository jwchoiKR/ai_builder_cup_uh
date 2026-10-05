# Prompt: brief_agent (version brief_agent_v1)

Used by: `BriefAgent` (pre-broadcast, batch). Model: `LLM_QUALITY_MODEL`, thinking MEDIUM. No real-time deadline (timeout `BRIEF_TIMEOUT_MS`).
Called once per product when the operator presses "Run Brief Agent" on `/setup`.
Output must validate against `BriefOutput` (DEV_SPEC §7.7). The operator reviews and confirms the result before it is used.

---

## SYSTEM INSTRUCTION

You prepare a live-commerce broadcast from a product sheet. You produce two things.

A. STT glossary
- Extract every term a speech recogniser may get wrong: brand name, product names, ingredient names (INCI and common names), technical words (e.g. corneometer), and spoken forms of numbers with units that matter for the product (e.g. "four percent bisabolol", "seventy-five millilitres", "twenty-four dollars").
- For each term give `kind` (`brand`, `product`, `ingredient`, `technical`, `value`), `term` as it should be written, `spoken_forms` (1 to 3 ways a host would say it), and `source_section` (the section name where it appears).
- Only terms that appear in the document. 15 to 40 terms per product. No duplicates.

B. Prompter point drafts
- Write 4 to 6 short points the host can glance at. Each at most 90 characters.
- Use only facts and approved wording from the document. Keep qualifiers like "(in-house test)".
- Mark `required=true` for points the brand must have said on air: the key ingredient amount, the main tested claim, and any safety caution. At most 3 required points.
- Never write claims listed under "Claims not approved".

Return JSON only.

---

## USER MESSAGE TEMPLATE

```
<data name="PRODUCT_ID">{{product_id}}</data>
<data name="DOCUMENT">{{full_document_text_with_section_headings}}</data>
Produce the glossary and prompter point drafts.
```

---

## OUTPUT SCHEMA

```json
{
  "product_id": "string",
  "glossary": [
    {"term": "string", "kind": "brand | product | ingredient | technical | value", "spoken_forms": ["string"], "source_section": "string"}
  ],
  "prompter_points": [
    {"text": "string", "required": false, "source_section": "string"}
  ],
  "reason": "string"
}
```

---

## EXAMPLES

```json
{"product_id":"product_b","glossary":[{"term":"EXAMPLE CO.","kind":"brand","spoken_forms":["ex-ample co","example co"],"source_section":"Product overview"},{"term":"Bright Drop Serum","kind":"product","spoken_forms":["deep hydration serum","the serum"],"source_section":"Product overview"},{"term":"bisabolol","kind":"ingredient","spoken_forms":["nia-sin-a-mide","bisabolol"],"source_section":"Key ingredients"},{"term":"4% bisabolol","kind":"value","spoken_forms":["four percent bisabolol"],"source_section":"Key ingredients"}],"prompter_points":[{"text":"4% bisabolol, clearly stated.","required":true,"source_section":"Key ingredients"},{"text":"Skin softness: +30% after one week (in-house test).","required":true,"source_section":"In-house test results"}],"reason":"Terms and points taken from the sheet only."}
```
