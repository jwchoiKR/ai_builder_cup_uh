# Viewer comments: how a comment is handled, and what was measured

Status 2026-10-09, branch `perf/realtime-overhaul` (local, not pushed). Scope: the comment path only. The speech path
(STT, judges, alerts) is unchanged.

Every number below is measured, one run each, on the real models on Vertex AI (global endpoint) with the two demo
products. The raw run reports are kept locally (`docs/eval/comments-1008/`, not in the repository). One run on small
sets: read the percentages with their counts.

## 1. The decision: answered by itself, or waits for a person

A question ends in one of two ways. Nothing else is decided while the show runs.

| outcome | when | what the viewer gets |
|---|---|---|
| answered by itself | triage says no person is needed **and** a draft passed every check | a reply marked "AI answer", text only |
| waits for a person | triage says a person must approve it, **or** no draft passed the checks | the reply the host says on air or the operator posts |

The rule the triage prompt gives the model: no person is needed only when the reply would be one fact read straight off
the product sheet, the same sentence for every viewer who asks. If the reply has to be reasoned out of the sheet, or it
touches the viewer's health or safety, what the product will achieve, test results, certificates, personal advice, or
anything the host or the shop would have to do, a person approves it.

The topic of a question (its intent, e.g. `price`, `shipping`) is still returned by triage but routes nothing when
triage gives the decision. It is used to pick the record answer for price and size, to fetch passages, and as the
fallback route when triage gives no decision (`data/policy/intents.json`). Statistics by topic are not built during
the show: the comments are analysed once after the broadcast (§2, "After the show").

## 2. The flow

```
viewer comment
  │
  ├─ 1. code: rate limit, links masked, e-mail / phone hidden, emoji-only and listed reactions settled      (no LLM)
  ├─ 2. Model Armor screen (deploy only): blocked comments never reach a model
  ├─ 3. triage agent, one call: kind (question / reaction / hide), product, topic, a normalised English question,
  │      language, a second question if the comment asks two things, and needs_approval + approval_reason
  ├─ 4. code: ids checked, product attributed, new group (or the group of the very same words)
  ├─ 5. code: route from triage's decision
  └─ 6. answer
        ├─ record answer   price, size: the value by code from the product record, worded by the reply phraser;
        │                  code keeps the wording only if the value is there and no other number was added
        ├─ cached answer   the same question again: the verified answer of this broadcast, no LLM
        └─ composed answer the composer writes from the sheet passages → code checks citations and numbers
                           → on a rejection the composer writes once more with the reasons
        every one of the three then passes the draft verifier (meaning, and "is this what the viewer asked?")
```

Who gets a question that waits for a person:

| approval reason | where it goes |
|---|---|
| health, claim, personal, host_line, unclear | the host's card with the suggested reply **and** the operator's list at once; the first of the two posts it, once |
| test_results, certification, outside (shipping, payment, the show itself), no product | the operator's list only |
| no draft passed the checks | the operator's list only |
| a comment with two questions | always waits for a person |

Other behaviour:

- **Hidden comments.** Profanity, insults aimed at people, spam and personal information are hidden. A negative
  opinion without abuse ("boo, not for me") is a reaction and stays visible (owner decision).
- **Prompt injection.** A comment that gives the system orders is hidden with `signal=injection`; a real question with
  an order appended stays a question and the order is ignored.
- **Stream problems.** "No sound", "frozen" are reactions with `signal=stream_issue`, shown to the operator.
- **No grouping by meaning** (owner decision). Triage is no longer given the open questions and returns no group
  pick, and the grouping rules are gone from `logic/grouping.py` (prompt `comment_triage_v10`); a comment is no longer
  triaged a second time because the list of open questions had changed. Only a comment that repeats a member's own words joins a question;
  every other wording is its own question with its own reply and its own row. A reply therefore never lands on a
  question it does not answer. The host's cards are ordered by the remaining terms of the score: the product on air,
  the topic's purchase weight, and the waiting time (the number of askers is 1 unless viewers typed the same words).
  A question the operator sends to the host is pinned ahead of the automatic ones.
- **Translation.** After a reply is posted, the reply translator adds it in the language of askers who wrote in
  another language. The reply never waits for it, and a translation whose numbers differ from the reply's is dropped.
- **Other currencies.** A price asked in another currency is answered in S$ with a note that the amount depends on
  the exchange rate (owner decision).
- **No source.** When the product information does not answer a question, no answer is suggested. The operator's
  reply box starts with one fixed sentence ("That isn't covered in our product information. Our team will check and
  get back to you."), editable, with a note only the team sees.

Rules that hold everywhere: the model proposes, code decides. No model output posts anything by itself; every id a
model returns is checked against the ids it was offered; a failed, late or invalid model call posts nothing and the
question goes to the operator. Triage and the composer are retried on a failed call (`TRIAGE_RETRIES`,
`COMPOSE_RETRIES`); the draft verifier is asked once more on a timeout or an error.

## 3. Code map

`backend/app/pipelines/comments.py` is the whole comment path, top to bottom in the order a comment travels:

| part | functions | what it does |
|---|---|---|
| intake | `submit_comment`, `_finish_armored` | stores the comment, prefilter, Model Armor result |
| triage | `process_comment`, `TriageQueue`, `_second_question`, `_note_language` | the triage call (with retry and batching under load), the second question of a comment, language |
| questions | `_same_words_group`, `_assign_question_locked`, `_finish_non_question` | a new question, or the open question a viewer already asked in the same words; reactions and hidden comments end here |
| routing | `_route`, `_approval_route`, `no_draft_locked`, `move_previous_product_questions_locked` | the two-way decision and who gets a waiting question |
| answering | `answer_group_locked`, `_record_answer`, `compose_for_group`, `_run_composer`, `draft_code_gate`, `_llm_check`, `apply_answer_locked`, `reply_again_locked` | record / cached / composed answer, the checks, posting |
| operator actions | `push_to_host`, `recall_from_host`, `assign_product`, `approve`, `write_answer`, `post_suggested`, `reject`, `unhide_comment` | what the operator's buttons do; an operator's own text is checked before it is posted |

Around it: `agents/` (one file per model call: `comment_triage`, `answer_composer`, `draft_verifier`,
`reply_phraser`, `reply_translator`), `prompts/*.md` (their prompts), `logic/record_answers.py` (price and size from
the record), `logic/grouping.py`, `logic/verify.py` (the code checks of a draft), `logic/reply_status.py` (the status
line a viewer sees under their own comment), `pipelines/translation.py`.

### After the show: what viewers asked (summary page)

Topics are not assigned to route anything during the show. When the broadcast ends, `pipelines/comment_insights.py`
reads the session's stored comments, questions and posted replies once (with `SESSIONS_FIRESTORE` from Firestore,
after the write queue is flushed; otherwise from the app's store) and the `CommentInsights` agent
(`prompts/comment_insights.md`, `LLM_QUALITY_MODEL`, deadline `SUMMARY_TIMEOUT_MS`) sorts the questions into topics
and marks the topics that are buying questions. It runs next to the recap, and the result is stored in the summary
document as `comment_insights`.

The model returns no numbers. Code counts, from the stored records: questions and viewers per topic and how they
ended (answered automatically, by the host or the team, unanswered), examples in the viewers' own words (never a
hidden comment), the wait from a comment to its reply (median and 95th percentile, automatic and by a person),
buying questions and how many of them went unanswered, questions for which no answer could be written from the
product information, why questions waited for a person, the languages of the questions, and comments and
questions per slice of the broadcast (1 minute up to 20 minutes of show, 5 minutes beyond) with the busiest slice
and the product on air in it. A key the agent was
not offered is ignored, a question it leaves out is "Other", a note with a digit in it is dropped. When the agent
fails, the topics are the labels triage stored with each question, and the page says so.

Checked on the real server on 10/9 (`frontend/e2e/summary-live.mjs`, 14 comments, then End broadcast): the block
was built from Firestore with 7 topics; one run, not a measurement of topic quality.

## 4. Settings

| setting | default | meaning |
|---|---|---|
| `TRIAGE_MODEL` | `gemini-3.8-flash` | the triage model (empty = `LLM_FAST_MODEL`) |
| `LLM_QUALITY_MODEL` | `gemini-3.8-flash` | the composer's model |
| `TRIAGE_TIMEOUT_MS`, `TRIAGE_RETRIES` | 10000, 2 | triage deadline and retries |
| `DRAFT_VERIFY_THINKING`, `DRAFT_VERIFY_TIMEOUT_MS` | MEDIUM, 8000 | the draft verifier |
| `RECORD_ANSWERS`, `RECORD_PHRASING` | true, true | price and size from the record; natural wording by the phraser |
| `COMPOSER_REVISE`, `COMPOSE_RETRIES` | true, 1 | one rewrite after a code-gate rejection; retry after a failed call |
| `SENSITIVE_APPROVAL` | both | host card and operator list at once |
| `GROUP_TTL_WAITING_SEC` | 3600 | how long a question waiting for a person stays open |

Removed on 10/9 as settled: `ROUTING` (two-way is the only routing), `GROUPING`, `MERGE_CHECK` and its agent (no
grouping by meaning), `RECORD_VERIFY`, `SECOND_QUESTIONS`, `REPLY_TRANSLATION` (always on).

## 5. For the other parts of the app: what this branch changes around the comment path

The comment path and the summary are built to the decisions above. The points where another part of the app meets
them, and what was changed there:

| where | what this branch does | what to know when merging |
|---|---|---|
| routing | triage's `needs_approval` decides; the intent table of `intents.json` is used only when triage gives none | recorded mock fixtures without `needs_approval` still route by intent, so tests written for intent routes keep passing |
| grouping | no grouping by meaning: triage gets no open questions and returns no group pick (`group_candidate_id` is ignored), `find_group` and its rules are removed, `TRIAGE_MAX_OPEN_GROUPS` is gone; `tests/test_mapping_grouping_routing.py` and `test_d304.py` lost the tests of those rules | the host's list no longer has "N asking" on one card. `test_bursts_api` and `test_demo_script_api` were rewritten for it: several questions per topic, asker counts summed over them, and the host's six places can be full of earlier questions |
| host cards | the score formula (`logic/ranking.py`) is unchanged; the asker term is 1 unless viewers typed the same words | ordering is by product on air, purchase weight and waiting time; an operator's push is still pinned first (`host_queue.push_slot`) |
| sensitive questions | host card and operator list at once (`SENSITIVE_APPROVAL=both`) | the older tests pin `host` in `tests/conftest.py` |
| spoken answers | unchanged: the host saying a suggested reply posts it after the cancel window | it replies to the askers of that one question |
| viewer page | a reply shows only its text and "AI answer" (no sources); a status line under the viewer's own comment; replies in the asker's language | `showSources` prop, default false |
| operator page | To do / Answered / All; one reply box per question (suggested reply as starting text, the standard no-source reply when there is none); no category strip | |
| summary | `SummaryDoc.comment_insights` and the "What viewers asked" card; the top counters use it when present | `GET /sessions/{sid}/summary` returns the extra key; the recap agent and its statistics are untouched |
| store | `store/session_mirror.py` wraps the store when `SESSIONS_FIRESTORE=true`; `store/firestore.py` is untouched | see `docs/comments-firestore.md`, "At the merge" |
| shared files touched | `pipelines/runtime.py` (agents wired, reply translation, waiting-question TTL), `bus.py` (viewer and host views of events), `providers/llm.py`, `models/session.py`, `models/agent_io.py`, `agents/inputs.py`, `config.py`, `main.py`, `context.py`, `tests/conftest.py` (new defaults pinned for older tests), `tests/helpers.py` | conflicts are expected in `config.py`, `conftest.py`, `test_prompts.py`, `pyproject.toml`, `uv.lock`, `HostScreen.tsx`, `operator/model.ts` |
| speech path | not changed (STT, judges, alerts, prompter, product switch) | |

New files of the comment path and summary: `agents/reply_phraser.py`, `agents/reply_translator.py`,
`agents/comment_insights.py` and their prompts; `logic/record_answers.py`, `logic/reply_status.py`;
`pipelines/translation.py`, `pipelines/comment_insights.py`; `store/session_mirror.py`;
`scripts/eval_comment_holdout.py`; the live checks `frontend/e2e/comments-live.mjs` and `summary-live.mjs`.

## 6. Measured: set 4, 240 comments never seen before

`data/eval/comment_holdout4_raw.jsonl`: 12 scenes, written without reading the prompts; 183 English (with Singlish),
the rest Japanese, Korean, Malay, Mandarin, Indonesian. Labelled independently (`comment_holdout4_gold.jsonl`, rules
in its README): 176 questions (74 may be answered automatically), 48 reactions, 16 to hide. The 7 low-confidence rows
are left out of every rate. Runs 1 and 2 ran at the same time, so their latencies are upper bounds.

| metric | 3.8-flash, run 1 | flash-lite, run 1 | flash-lite, run 2 (after the changes below) |
|---|---|---|---|
| kind (question / reaction / hide) | 233/233 (100%) | 233/233 (100%) | 232/233 (99.6%) |
| auto or approval, as the gold says | 149/171 (87.1%) | 153/171 (89.5%) | 155/171 (90.6%) |
| the same, without rows defensible either way | 135/152 (88.8%) | 140/152 (92.1%) | 141/152 (92.8%) |
| auto answers posted where the gold allows one | 52/73 (71.2%) | 60/73 (82.2%) | 60/73 (82.2%) |
| auto answers posted where the gold does not | 4 | 6 | 3 |
| replies to an injection comment | 0 | 0 | 0 |
| stream problems flagged | 6/6 | 5/6 | 6/6 |
| wrong merges | 0 | 0 | 0 |
| triage latency p50 / p95 | 3.3 / 15.0 s | 3.3 / 7.3 s | 4.3 / 8.1 s |
| comment to reply, composed p50 / p95 | 9.9 / 24.1 s | 6.3 / 13.3 s | 8.6 / 18.3 s |
| comment to reply, record p50 / p95 | 6.0 / 7.2 s | 4.3 / 7.0 s | 6.9 / 9.3 s |

Run 1 is the accuracy on new comments. Run 2 is the same set after it was read, so it shows whether the changes
worked, not accuracy on new comments. English only, run 2: kind 177/178, auto or approval 106/119 (89.1%), one auto
answer posted where the gold does not allow one, 12 questions that could have been answered waited for a person.

Changes between run 1 and run 2 (principles, no phrase lists): the triage rule of §1 written out; safety of a body
part, side effects, how long an effect lasts and requests to the host named under their approval reasons; the draft
verifier decides first whether the reply is a direct answer to what the viewer asked (`answers`: direct / partial /
no) and anything but `direct` is not posted; the verifier is asked once more after an error.

`gemini-3.8-flash` is the default model (owner decision: it is expected to be the stronger model; on 10/8 and 10/9
its calls timed out often, which is where most of its missed answers come from: "draft_check_error",
"draft_check_timeout"). The live test server was run with `gemini-3.5-flash-lite` on those days.

### Final check on the cleaned-up code (10/9)

The same 240 comments after the settings clean-up, both models at the same time (latencies are upper bounds):

| metric | 3.8-flash (default) | flash-lite |
|---|---|---|
| kind | 232/233 (99.6%) | 233/233 (100%) |
| auto or approval, as the gold says | 145/171 (84.8%) | 156/171 (91.2%) |
| the same, without rows defensible either way | 132/152 (86.8%) | 140/152 (92.1%) |
| auto answers posted where the gold allows one | 47/73 (64.4%) | 58/73 (79.5%) |
| auto answers posted where the gold does not | 3 (0 without rows defensible either way) | 1 (0) |
| replies to an injection comment | 0 | 0 |
| stream problems flagged | 6/6 | 6/6 |
| triage latency p50 / p95 | 6.3 / 17.2 s | 4.2 / 9.8 s |
| comment to reply, composed p50 / p95 | 20.9 / 43.7 s | 7.7 / 16.6 s |
| comment to reply, record p50 / p95 | 9.8 / 17.3 s | 6.5 / 14.9 s |

On both days measured (10/8, 10/9) `gemini-3.8-flash` answered fewer questions and was slower than flash-lite.

After the grouping machinery was taken out of triage (prompt `comment_triage_v10`, no open questions in the input, no
second triage call), two more runs on flash-lite: kind 233/233 both; auto or approval 148/171 (86.5%) and 153/171
(89.5%); auto answers posted where the gold does not allow one 1 and 3; triage p50 / p95 3.7 / 6.5 s and 3.9 / 7.4 s;
composed reply p50 / p95 6.9 / 12.3 s and 7.8 / 13.6 s. The runs before it gave 89.5% to 91.8% on the same set: one
run differs from the next by a few points, so a change of this size is not resolved by single runs.

Browser check on the running server (`frontend/e2e/comments-live.mjs`, real models, Firestore writes on), 8 of
8 steps passed: a viewer joins and asks the price, the reply appears as "AI answer" with no sources shown; a pregnancy
question posts nothing by itself and reaches the operator with a suggested reply, which the viewer sees after the
operator posts it; a shipping question gets no suggestion, the standard no-source reply is offered with the note only
the team sees, and is posted; a reaction gets no reply; an insult is hidden from the viewer state; a Korean size
question is answered with the reply also in Korean. Writer counters after it: 0 retries, 0 lost writes.

### What still fails (flash-lite, run 2)

1. Posted where the gold does not allow it, 3: two "is it ok for sensitive skin?" (Malay, Japanese) answered "Yes, it
   is suitable for sensitive skin.", which the sheet states (gold: approval; owner decision open); "set 62 plus pouch
   confirm or not" answered with the set price only.
2. Could have been answered, waited for a person, 13: triage sent a plain question to approval ("what does allantoin
   even do", "what promo is running now"); the composer found no passage for an answer that needs a step of reasoning
   ("can i keep it in my car", "so the set is cheaper than buying both separately?", "already has spf?").
3. Waiting questions with a suggested reply: 50 of 114 (41 verified, 9 unverified). 64 had none: 43 not answered by
   the sheet, 21 outside the product (shipping, payment), for which no source exists.

## 7. Earlier sets

Sets 1 to 3 (`comment_holdout{,2,3}_*`) were used while the prompts were revised. The last run on set 3 (flash-lite): kind 99.6%, auto or
approval 91.9% (94.7% without rows defensible either way). Those sets had been seen when these numbers were taken.

## 8. Open items

- Owner decisions: skin-type suitability the sheet states ("ok for sensitive skin?") automatic or approval; the
  default model once `gemini-3.8-flash` is stable.
- The largest lever for automatic answers is the product sheet itself: one plain line per frequent question (SPF,
  storage, where to apply, set versus single items). A shop policy document (shipping, payment, returns) would give
  the 21 outside-the-product questions a source.
- Without grouping, viewers who ask the same approval question in different words each make their own row for the
  operator and their own host card, and the host's spoken answer replies to the askers of one of them. The host's
  list holds six questions: when it is full of earlier ones, a later question waits outside it until the operator
  sends it (seen in `test_bursts_api`). A trial that grouped only the questions waiting for a person (10/9, sets 3
  and 4) made 0 wrong merges but found 2 of 20 and 1 of 5 of the labelled same-question pairs; it was not kept.
- Firestore: every session is written by `store/session_mirror.py` (`SESSIONS_FIRESTORE=true`), read back after a
  restart and evicted from memory after it ended; one instance only. See `docs/comments-firestore.md` §6.
- Not measured: a fifth unseen set after the run-2 changes, real viewers, bursts beyond 1 comment per 1.5 s, Model
  Armor on, cost per comment.
