# Prompt: comment_triage_batch (version comment_triage_batch_v1)

Used by: `CommentTriage.run_batch`. Model: `LLM_FAST_MODEL`, thinking MINIMAL. Deadline `TRIAGE_BATCH_TIMEOUT_MS`.
Called only when comments pile up while every triage slot is busy (adaptive micro-batch, PLANNING 5.1.2): up to `TRIAGE_MAX_BATCH` comments in one call. A single waiting comment still uses `comment_triage.md`.
The system instruction is built at load time: the SYSTEM INSTRUCTION of `comment_triage.md`, then the text below, then the EXAMPLES of `comment_triage.md`. The classification rules therefore never drift apart.
Output must validate against `CommentTriageBatchOutput`.

---

## SYSTEM INSTRUCTION

### Several comments in one request

This request carries COMMENTS instead of one COMMENT: a list of `{i, context_product_id, recent_host_line, comment}`.
- Classify every item on its own with the rules above. `context_product_id` is that item's CONTEXT_PRODUCT_ID and `recent_host_line` its RECENT_HOST_LINE.
- Items never influence each other.
- Return `{"items": [...]}` with exactly one object per item, in any order. Each object is the single-comment output plus `"i"`, the item's index.
- The examples below show one comment each; in this request wrap the objects in `items`.

---

## USER MESSAGE TEMPLATE

```
<data name="PRODUCTS">{{products_compact_json}}</data>
<data name="INTENTS">{{intent_names_json}}</data>
<data name="SLOTS">{{condition_slots_json}}</data>
<data name="COMMENTS">{{comments_json}}</data>
Classify every item of COMMENTS.
```

`comments_json`: `[{i, context_product_id, recent_host_line, comment}]`, each comment truncated to `MAX_COMMENT_CHARS`; `recent_host_line` as in `comment_triage.md`.

---

## OUTPUT SCHEMA

```json
{"items": [{"i": 0, "kind": "...", "...": "the comment_triage output fields"}]}
```
