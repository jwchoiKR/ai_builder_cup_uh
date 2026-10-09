# Viewer comments in Firestore: what is stored, under which keys, and why

Status 2026-10-09. For whoever merges the comment branch (`perf/realtime-overhaul`) with `multi_agent_test`.
Database: `live-studio` (Firestore Native, us-central1) in project `ai-budiler-cup-uh-team-pjt`.

**Since the merge into `multi_agent_test` (D-428, 10/10):** `session_mirror.py` is gone. `STORE=firestore`
(`backend/app/store/firestore.py`) is the one writer: it writes and reads back the five comment collections, keeps
`read()`/`read_session()`, the `status()` shape and eviction of ended sessions. `SESSIONS_FIRESTORE` and
`SESSIONS_FIRESTORE_DATABASE` are no longer used: set `STORE=firestore` (database `FIRESTORE_DATABASE`). The paths and
fields below are unchanged. The rest of this file describes the mirror as it was before the merge.

Short version (before the merge): with `SESSIONS_FIRESTORE=true` every session is written to Firestore by one module,
`backend/app/store/session_mirror.py`. Memory holds only the shows the process is working on: a session that is not
in memory (the process restarted, or the session was evicted after it ended) is read back from Firestore when it is
opened. This file is the contract for the five documents of the comment path (paths, keys, fields, reasons), and §6
describes the store.

## 1. Where the documents live

```
sessions/{session_id}                         one broadcast                      ses_<ULID>
  ├─ comments/{comment_id}                    one viewer comment                 cm_<ULID>
  ├─ analyses/{analysis_id}                   what triage said about one comment an_<ULID>
  ├─ groups/{group_id}                        one question and its state         grp_<ULID>
  ├─ answers/{answer_id}                      one draft or written reply         ans_<ULID>
  ├─ messages/{message_id}                    one reply or notice viewers see    msg_<ULID>
  └─ segments, transcripts, alerts, events, agent_calls, summary   (speech path and shared; not described here)
```

Collection names are the constants of `backend/app/store/base.py` (`SUBCOLLECTIONS`); the models are in
`backend/app/models/session.py`. A document is the model's `model_dump(mode="json")`: the field names below are the
Firestore field names.

### Keys

- **Document id = the model's own id field** (`comment_id`, `group_id`, ...). The id is also a field of the document,
  so an exported document is complete without its path.
- **Ids are a prefix and a ULID** (`backend/app/ids.py`): 48 bits of milliseconds, then 80 random bits, in Crockford
  base32. Reasons: no counter to coordinate (nothing to read before a write); ids sort by creation time, so
  "comments in order" needs no extra index within one session; the prefix says what a bare id refers to in a log.
  With `LLM_PROVIDER=mock` ids are counters (`cm_000001`) so test fixtures stay stable; those never reach Firestore
  in a deployed build.
- **Everything hangs under the session.** A broadcast is read, exported and deleted as one unit, and no query during
  the show crosses sessions. An analysis across broadcasts uses a collection-group query (§5).
- **Times are integers, epoch milliseconds, UTC** (`received_at`, `first_at`, `created_at`, ...), not Firestore
  timestamps: the same number is used by the event stream and the browser, so nothing is converted on the way.

## 2. The documents

### `comments/{comment_id}`: what the viewer wrote

| field | type | meaning |
|---|---|---|
| `comment_id` | string | key |
| `author_id`, `author_name` | string | the viewer (anonymous id, display name) |
| `text` | string | the comment as typed, in full |
| `received_at` | int (ms) | arrival time |
| `source` | `viewer` / `script` / `pool` | typed by a viewer, or injected by the demo script or the eval pool |
| `kind` | `pending` / `question` / `reaction` / `hide` | `pending` until triage answers |
| `visibility`, `hide_category` | `visible` / `hidden`; `profanity` / `harassment` / `spam` / `link` / `personal_info` / null | hidden comments stay stored; viewers and the host never receive their text |
| `language`, `translation_en` | string / null | ISO 639-1 of the comment; its English translation when it is not English (for the team) |
| `signal` | `stream_issue` / `injection` / null | a stream problem report, or an attempt to give the system orders |
| `armor` | `blocked` / `unscreened` / null | Model Armor result (deploy only) |
| `reply_status` | `checking` / `host` / `team` / `answered` / null | the status line the viewer sees under their own comment |
| `analysis_id`, `group_id` | string / null | links to the two documents below |

### `analyses/{analysis_id}`: what the model said, kept apart from the comment

| field | type | meaning |
|---|---|---|
| `analysis_id`, `comment_id` | string | key, and the comment it is about |
| `output` | map | the triage output as validated: `kind`, `intent`, `product_id`, `condition_slots`, `canonical_question`, `language`, `translation_en`, `signal`, `second_question`, `needs_approval`, `approval_reason`, `reason` |
| `product_id`, `product_basis`, `context_product_id` | string / null | the product code attributed (which may differ from the model's), on what basis, and the product on air when the comment arrived |
| `route`, `route_reason` | `AUTO` / `HOST` / `OPERATOR`; string | the route code decided from it |
| `source` | `llm` / `prefilter` / `cache` / `fallback` / `armor` / `unscreened` | who classified it |
| `latency_ms` | int / null | time of the triage call |

Why a separate document: the comment is a fact (a viewer wrote this); the analysis is one model's opinion of it. Kept
apart, a comment can be triaged again (a second question, an operator unhiding it) without rewriting the viewer's
record, and an audit can show exactly what the model returned next to what code then decided (`output.product_id`
against `product_id`, `output.needs_approval` against `route`).

### `groups/{group_id}`: one question and where it stands

| field | type | meaning |
|---|---|---|
| `group_id` | string | key |
| `canonical_question` | string | the question in plain English, as triage normalised it |
| `product_id`, `intent`, `condition_slots` | string / null; string; map of string | product, topic label, and conditions (skin type, life stage, ...) |
| `member_comment_ids`, `unique_author_ids` | array of string | the comments in it and who asked |
| `first_at`, `last_at` | int (ms) | first and latest comment |
| `needs_approval`, `approval_reason` | bool / null; string / null | **the two-way decision**: must a person approve the reply, and why (`health`, `claim`, `test_results`, `certification`, `personal`, `outside`, `host_line`, `unclear`) |
| `route`, `route_reason` | `AUTO` / `HOST` / `OPERATOR`; string | who settles it (`auto`, `approval`, `no_verified_answer`, `previous_product`, ...) |
| `status` | `new` / `composing` / `ready` / `auto_answered` / `needs_review` / `answered` / `rejected` / `closed` | where it stands |
| `answer_id`, `published_message_id` | string / null | the current draft, and the reply that was posted |
| `host_slot`, `on_host_since`, `pinned_by_operator_at`, `recalled_at`, `host_verbal_answer_transcript_id`, `host_confirmed` | | the host card and the spoken answer |
| `closed_reason`, `score`, `version` | | why it closed, queue score, a counter raised on every change |

The group is the unit everything acts on: one draft, one host card, one operator row, one reply. Questions
are not grouped by meaning, so most groups have one member: a group is in practice "one question".

### `answers/{answer_id}`: a draft, or a reply an operator wrote

| field | type | meaning |
|---|---|---|
| `answer_id`, `group_id` | string | key, and its question |
| `text` | string | the reply text (empty when the product information does not answer the question) |
| `citations` | array of map `{passage_id, quote}` | the passages it rests on |
| `origin` | `ai` / `operator_edit` / `operator_written` | who wrote it |
| `record` | bool | true when the value came from the product record by code (price, size) |
| `verified`, `verify_errors` | bool; array of string | passed every check, or the reasons it did not |
| `needs_human`, `cache_key`, `created_at` | | the composer's own flag, the key of the answer cache, creation time |

An answer is never changed after it is written: a rewrite or an operator's edit is a new document, and the group's
`answer_id` moves to it. The earlier drafts stay as the record of what was suggested.

### `messages/{message_id}`: what viewers actually saw

| field | type | meaning |
|---|---|---|
| `message_id` | string | key |
| `kind` | `ai_answer` / `host_answer` / `brand_answer` / `notice` / `correction_notice` | posted by itself, said by the host, posted by the operator, or a notice |
| `text` | string | the posted text |
| `translations` | map `language → text` | the reply in the askers' languages, added after posting |
| `group_id`, `reply_to_comment_ids`, `reply_to_author_names` | | the question and the askers it replies to |
| `citations` | array of map | as on the answer |
| `state`, `created_at`, `publish_at`, `published_at` | `pending` / `published` / `cancelled`; int (ms) | a host's spoken answer is `pending` for a 2 s cancel window |
| `idempotency_key` | string | the same reply is never posted twice |

## 3. How one comment becomes documents

```
"how much is the cream?"                       →  comments/cm_…      kind=pending
triage returns                                 →  analyses/an_…      output.needs_approval=false
                                                  comments/cm_…      kind=question, analysis_id, group_id
new question                                   →  groups/grp_…       needs_approval=false, route=AUTO, status=composing
record answer, checked                         →  answers/ans_…      record=true, verified=true
posted                                         →  messages/msg_…     kind=ai_answer, state=published
                                                  groups/grp_…       status=auto_answered, published_message_id
                                                  comments/cm_…      reply_status=answered
```

A question that waits for a person stops at `groups.status = ready` (host card and operator list) or `needs_review`
(operator only), and the message is written when the host says the reply or the operator posts it.

## 4. Why it is shaped this way

- **The decision is stored where it is used and where it was made.** `groups.needs_approval` is what the code acts
  on; `analyses.output.needs_approval` is what the model returned. The accuracy of the two-way decision can be
  measured from stored broadcasts by comparing them with what finally happened (`messages.kind`).
- **Suggested, approved and posted are three documents** (`answers`, the group's state, `messages`), so "what did the
  AI suggest", "who approved it" and "what did viewers see" are each one read, and an edited reply does not overwrite
  the suggestion it started from.
- **No arrays inside arrays, no document that grows without limit.** Firestore has no nested arrays and a document is
  at most 1 MiB. Every field of the five documents is a scalar, a flat array of strings, an array of small maps, or a
  small map, so they are written as native fields and can be filtered in a query (the show's store writes a document
  with a nested array as one JSON string, which cannot be filtered; none of these five has one). Checked on
  10/9 against the models' types. The two arrays that grow are `member_comment_ids` and `unique_author_ids`; with
  no grouping by meaning they hold the viewers who typed the very same words.
- **Writes never wait for the network.** The runtime reads and writes under the session lock many times per comment,
  so memory is the working copy and Firestore is written behind it in order. Firestore is a durable copy and a source
  for analysis after the show, not the live source of truth (§6).
- **Topic statistics are not stored during the show.** `groups.intent` is a label. The planned summary of "what was
  asked most" is one analysis after the broadcast over `comments` and `groups` of the session.

## 5. Reading it back

| question | read |
|---|---|
| everything about one broadcast | the five subcollections of `sessions/{session_id}` |
| the chat in order | `comments` ordered by `received_at` (or by document id: ULIDs sort by time) |
| answered by itself / waited for a person | `groups` where `needs_approval == false` / `== true`; outcome in `status` |
| what waited and why | `groups` where `needs_approval == true`, grouped by `approval_reason` |
| questions nobody answered | `groups` where `status in [needs_review, ready]` at the end of the show |
| wrong automatic answers to review | `messages` where `kind == ai_answer`, joined to `groups` and `comments` by id |
| the same across broadcasts | a collection-group query on `comments` or `groups` (needs a collection-group index on the filtered field) |

Single-field filters within one session need no composite index. A filter on one field with an order on another
(for example `needs_approval == true` ordered by `first_at`) needs a composite index; none is defined yet because
nothing in the app queries Firestore during a show.

## 6. The session store

```
runtime ──put/get/query──▶ SessionMirrorStore ──every call, unchanged──▶ MemoryStore (the shows being worked on)
                                 │  a write under sessions/… is also queued
                                 ▼
                          MirrorWriter: one ordered queue, one background task, batched commits
                                 ▼
                          Firestore `live-studio`:  sessions/{sid}  and  sessions/{sid}/<collection>/{id}
```

- **During a show nothing waits on the network.** Reads and writes go to memory; the queue is sent every 0.25 s.
  Writes to one document within a batch are coalesced (the latest wins); a batch is at most 400 documents and 6 MiB;
  a failing commit is retried 5 times with backoff before anything later is sent, then counted as lost and logged; a
  document over 900 kB is not sent. At shutdown the queue is flushed for up to 8 s.
- **What is written:** the session document and every collection of the session (comments, analyses, groups,
  answers, messages, segments, transcripts, alerts, events, agent calls, summary). Not written: `transcript.interim`
  events (several per second, of no use after the show), setup state, agent calls outside a session. A document with
  an array inside an array is written as one JSON string field `_json` (Firestore has no nested arrays); none of the
  five comment documents needs it.
- **Recovery.** `get` or `query` for a session that memory does not have reads the session document and all its
  collections from Firestore once (`MirrorWriter.read_session`) and loads them into memory. Then
  `Runtimes.session_loaded` moves the event numbers ahead by 10 000 (browsers skip numbers they have seen, and the
  last events of the old process may not have reached Firestore), and a live show's one-second tick and promo end
  timers run again (`SessionRuntime.resume`). An unknown session id is not looked up again for 30 s.
- **Eviction.** `SESSION_EVICT_AFTER_SEC` (default 900) after a show's summary is written, `Runtimes.evict` drops the
  ended session from memory: only when nothing of it is still queued and no write was lost, so the copy that stays is
  complete. Opening it later (the summary page) reads it back. A live show is never evicted.
- **Deleting a session** deletes it in Firestore only if this process wrote to it or loaded it: the database is
  shared.
- **Counters** are in `/api/health` under `store_status`: queue depth, last commit, retries, lost writes, sessions
  loaded and evicted.
- **Tests never reach the real database**: without an injected client the writer refuses to start under pytest
  (`tests/firestore_fake.py`, `tests/test_session_mirror.py`).

| setting | default | meaning |
|---|---|---|
| `STORE` | memory | `firestore`: write every session to Firestore and read it back when it is not in memory (needs `GCP_PROJECT`); replaces `SESSIONS_FIRESTORE` (D-428) |
| `FIRESTORE_DATABASE` | `live-studio` | the database; replaces `SESSIONS_FIRESTORE_DATABASE` (D-428) |
| `SESSION_EVICT_AFTER_SEC` | 900 | an ended session leaves memory this long after its summary; 0 keeps every session in memory |

### Limits

- **One instance.** One process owns a show; Firestore is behind memory by the flush interval and is not read while
  the show is in memory. Two instances would each hold their own copy of a live show. Running several instances
  needs an owner per show and a way to pass events between instances; that is not built.
- **A crash loses what was still queued**, at most the flush interval of writes, and the interim transcripts.
- **Timers of the old process do not come back**: the cancel window of a pending post, alert escalations, question
  holds, a switch countdown, the demo feed. The tick and promo end timers do.
- **Loading reads the whole session**, every event included. Not measured on a long show.

### At the merge with `multi_agent_test`

`multi_agent_test` has its own `STORE=firestore` (`store/firestore.py`, D-354, D-369): memory as the read model, a
write-behind mirror at the same paths, read-back on first touch. The two do the same job at the same paths with the
same `_json` convention, so documents written by one can be read by the other. This branch leaves `store/firestore.py`
untouched and adds `store/session_mirror.py` next to it; `make_store` uses `STORE=firestore` when it is set and
`SESSIONS_FIRESTORE` only with `STORE=memory`. One of the two should be kept: what this one adds is eviction of ended
sessions and the read used by the summary's comment analysis.

### Checked on the real database (2026-10-09)

Server with the comment collections written to Firestore (the first version of the store, `STORE=memory`), six comments through the API (a price question, a pregnancy
question, a shipping question, a reaction, an insult, a size question in Korean), then read back from `live-studio`
(session `ses_01M4EBGGRAA5DXTFZV38EZBR10`, left in the database):

- 6 `comments`, 6 `analyses`, 4 `groups`, 3 `answers`, 2 `messages`: the same ids as the app's own state.
- Every field of the comments and messages equals the app's copy; of the groups, every field but `score`.
  `score` is the host-queue score, recomputed in memory on every read; the stored value is the one of the last save.
- The two-way decision is stored as decided: price and size `needs_approval=false`, `route=AUTO`, `auto_answered`;
  pregnancy `true / health`, `HOST`, `ready`; shipping `true / outside`, `OPERATOR`, `needs_review`. The insult is
  stored with `visibility=hidden`; the Korean reply has `translations.ko`.
- Nothing else was written under that session: no session document, no events, transcripts, alerts, segments or
  agent calls.
- Writer counters after the run: 21 commits, 81 writes, 0 retries, 0 lost.

Restart and eviction, same day (`SESSIONS_FIRESTORE=true`, session `ses_01M4EPS2S0D1GBDKAQXCG1RCH9`): a live show with
three comments, then the server process was killed and a new one started. Opening the session in the new process
took 5.2 s and gave back the live show with its 3 comments, 3 questions and the host card; a new comment was triaged
and answered; after End broadcast the summary was written with the comment analysis read from Firestore; the session
left memory after the eviction delay (set to 25 s for the check) and opening the summary again took 1.2 s and
returned the same recap. Writer counters: 0 retries, 0 lost writes. One run on a short show.

Not checked: a long show, a burst of comments, Firestore being unreachable during a show (covered by tests with a
fake client only), and the deployed service.

## 7. Open points

- **Personal data.** `comments.text` and `author_name` are stored as typed, including comments hidden for
  `personal_info` (a phone number, an address). A retention period or a redacted copy for hidden comments is not
  decided.
- **Retention.** No TTL policy on the database; sessions stay until deleted.
- **Several instances.** See the limits in §6.
- **Security rules.** Browsers never read Firestore; only the Cloud Run service account does. The rules should deny
  client access to these collections.
- **Dynamic values.** Prices and promotions are read from `data/` files, not from Firestore.
