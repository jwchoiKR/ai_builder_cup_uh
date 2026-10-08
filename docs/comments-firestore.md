# Viewer comments in Firestore: what is stored, under which keys, and why

Status 2026-10-09. For whoever merges the comment branch (`perf/realtime-overhaul`) with `multi_agent_test`.
Database: `live-studio` (Firestore Native, us-central1) in project `ai-budiler-cup-uh-team-pjt`.

Short version: the comment path writes its own five collections to Firestore through one small module,
`backend/app/store/comment_mirror.py`, switched on with `COMMENTS_FIRESTORE=true`. It writes nothing else and reads
nothing, so it runs next to whatever the main store is (`STORE=memory`, or the show's Firestore store for sessions,
transcripts, alerts and events). This file is the contract for those five documents: paths, keys, fields, the
reasons, and what to do at the merge.

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

## 6. The module, and how it fits the show's Firestore store

Ownership (agreed 10/9): the show's store (`store/firestore.py`, D-354, D-369) keeps sessions, transcripts, alerts,
segments, events and agent calls; the comment collections are the comment path's to write.

```
runtime ──put/get──▶ CommentMirrorStore ──every call, unchanged──▶ the app's store (memory, or the show's Firestore store)
                            │
                            └─ a write to comments / analyses / groups / answers / messages is also queued
                                      │
                               CommentWriter: one ordered queue, one background task, batched commits
                                      ▼
                            Firestore `live-studio`:  sessions/{sid}/<collection>/{id}
```

- **`CommentMirrorStore`** wraps the store `make_store()` built (`store/__init__.py`). Reads, queries and every write
  go to the wrapped store first, so the runtime behaves exactly as without it and never waits on the network. Only
  paths of the form `sessions/{sid}/<one of the five collections>` are also queued (`session_of()`); a transaction's
  comment writes are queued as one group after it succeeded.
- **`CommentWriter`** sends the queue in order. Writes to one document within a batch are coalesced (the latest
  wins); a batch is at most 400 documents and 6 MiB; a failing commit is retried 5 times with backoff before anything
  later is sent, then counted as lost and logged; a document over 900 kB is not sent; at shutdown the queue is flushed
  for up to 8 s (`aclose`, called from the app's lifespan). Its counters are in `/api/health` under
  `store_status.comments` (queue depth, last commit, retries, lost writes, last error).
- **Deleting a session** removes only its documents in the five collections, and only for a session this process
  wrote comment documents for: the database is shared, the session document and the other collections belong to the
  show's store.
- **Nothing is read from Firestore.** After a restart the comment documents of an earlier show are in Firestore but
  not in memory (see open points).
- **Tests never reach the real database**: without an injected client the writer refuses to start under pytest
  (`tests/firestore_fake.py` is the fake; `tests/test_comment_mirror.py`).

| setting | default | meaning |
|---|---|---|
| `COMMENTS_FIRESTORE` | false | write the five collections to Firestore (needs `GCP_PROJECT`) |
| `COMMENTS_FIRESTORE_DATABASE` | `live-studio` | the database |

### At the merge with `multi_agent_test`

1. `store/firestore.py` is untouched on this branch (the earlier full store of this branch is removed), so the team's
   file merges as it is. `store/__init__.py` conflicts in `make_store`: keep both, the team's `FirestoreStore(settings)`
   and the `COMMENTS_FIRESTORE` wrap after it.
2. The show's store mirrors every `put` today. To give the five collections one writer, skip them there (a path
   test like `session_of()` in its enqueue), or leave `COMMENTS_FIRESTORE` off until that is done; with both on, the
   same documents are written twice to the same paths (harmless, wasteful).
3. `main.py`: this branch calls `ctx.store.aclose()` at shutdown with the same two lines as D-354; keep one copy.
4. `COMMENTS_FIRESTORE_DATABASE` can be dropped for the team's `FIRESTORE_DATABASE` (same default).
5. `pyproject.toml` / `uv.lock`: both branches add `google-cloud-firestore`; keep one line and run `uv lock`.
6. The show's store reads a session back after a restart. If it stops writing the comment collections it also stops
   reading them back: a show that continues on a new instance would have its transcripts and alerts but not its open
   questions. Either the show's store keeps reading the five collections, or a read-back is added here.

### Checked on the real database (2026-10-09)

Server with `COMMENTS_FIRESTORE=true STORE=memory`, six comments through the API (a price question, a pregnancy
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

Not checked: a long show, a burst of comments, Firestore being unreachable during a show (covered by tests with a
fake client only), and the deployed service.

## 7. Open points

- **Personal data.** `comments.text` and `author_name` are stored as typed, including comments hidden for
  `personal_info` (a phone number, an address). A retention period or a redacted copy for hidden comments is not
  decided.
- **Retention.** No TTL policy on the database; sessions stay until deleted.
- **Security rules.** Browsers never read Firestore; only the Cloud Run service account does. The rules should deny
  client access to these collections.
- **Dynamic values.** Prices and promotions are read from `data/` files, not from Firestore.
