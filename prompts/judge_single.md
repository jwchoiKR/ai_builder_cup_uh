# Prompt: judge_single (version judge_single_v1)

Used by: `UtteranceJudge` agent when `JUDGE_MODE=single`. Model: `LLM_FAST_MODEL`, thinking MINIMAL.
One call does everything in `utterance_judge.md` plus everything in `fact_checker.md`.
Retrieval runs BEFORE this call (same passages as the split mode, same timeout).
Output must validate against `JudgeSingleOutput` = `UtteranceJudgeOutput` + a `facts` field of type `FactCheckOutput` (DEV_SPEC §7.3).

## HOW TO BUILD THIS PROMPT

Do not duplicate text by hand. Build the system instruction at load time:

1. Take the SYSTEM INSTRUCTION of `utterance_judge.md` verbatim (Jobs 1 to 4).
2. Append a section `### Job 5. Product facts` containing the SYSTEM INSTRUCTION of `fact_checker.md` from "What to check" to the end of "Output rules", verbatim.
3. Append:

```
### Combined output
Return one JSON object with all fields of the Job 1-4 schema plus a field "facts" that follows the Job 5 schema
({"claims":[...],"reason":"..."}). Compliance and facts are independent: a sentence can have both a compliance
violation and a contradicted fact.
```

## USER MESSAGE TEMPLATE

```
<data name="CURRENT_PRODUCT">{{current_product_json}}</data>
<data name="RUN_SHEET">{{run_sheet_compact_json}}</data>
<data name="APPROVED_CLAIMS">{{approved_claims_of_current_product_json}}</data>
<data name="RULES">{{rules_compact_json}}</data>
<data name="ACTIVE_ALERTS">{{active_alerts_json}}</data>
<data name="OPEN_QUESTIONS">{{open_questions_json}}</data>
<data name="PROMPTER_POINTS">{{prompter_points_json}}</data>
<data name="HOST_CUES">{{host_cues_json}}</data>
<data name="SWITCH_CONTEXT">{{switch_context_json}}</data>
<data name="ACTIVE_PROMO">{{active_promo_json_or_null}}</data>
<data name="SET_OFFERS">{{set_offers_json}}</data>
<data name="SOURCE">{{passages_json}}</data>
<data name="RECENT_TRANSCRIPT">{{last_two_final_transcripts_json}}</data>
<data name="UTTERANCE">{{utterance_text}}</data>
Return the combined JSON verdict for UTTERANCE.
```

## EXAMPLES
Use examples A to F of `utterance_judge.md` with `"facts":{"claims":[],"reason":"..."}` added, plus examples A and B of `fact_checker.md` wrapped into the combined shape. Generate the wrapped examples at load time from the two files so they never drift.
