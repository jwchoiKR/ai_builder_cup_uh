# Decisions

Format (DEV_SPEC §0.3): `D-xxx: <decision>. Reason: <reason>`. Newest last.

## P0 Foundations (2026-10-01)

D-001: The repository root is `live-studio/` inside the delivered pack folder. `data/` and `prompts/` are byte-identical copies, checked by SHA-256; the pack files are left untouched. Reason: §4.2 names the root `live-studio/`, and README step 2 says to create the layout and copy the pack into it.

D-002: `.env.example` was rebuilt from `.env` by emptying `GCP_PROJECT`. The result is 3,863 bytes, the same as the delivered file. `.env` itself is not committed (`.gitignore`). Reason: the pack's `.env.example` had been renamed to `.env` and filled in, so the original was no longer in the folder. The keys and defaults match §5 (`tests/test_config.py` checks this).

D-003: `.env` is read from the repo root. Relative `DATA_DIR` and `PROMPTS_DIR` resolve against `backend/`, not the working directory. Reason: the defaults `../data` and `../prompts` are relative to `backend/`, and scripts and tests must work from any directory.

D-004: Settings validation fails at startup when:
- a Google provider is configured and `GCP_PROJECT` is empty;
- `RETRIEVER=vertex_search` is set and `VERTEX_SEARCH_DATA_STORE_ID` is empty.

`DEMO_TOOLS_ENABLED` becomes false when `APP_ENV=cloud` and the key is not explicitly set. Reason: §5 says "required when ..." and "MUST be false in cloud unless explicitly set". Failing at startup is the simplest way to keep both rules.

D-005: Structured output uses `response_mime_type="application/json"` with `response_json_schema=<pydantic model>.model_json_schema()`. The reply text is validated with our own pydantic model, not with `response.parsed`. Reason: VERIFIED §2.4 shows two problems:
- `response_schema=<pydantic class>` silently returned `{}` for `dict[str, str|None]` fields;
- `response.parsed` hides validation errors.

D-006: SDK retries stay off (`retry_options` unset). `LLMClient` retries once on HTTP 5xx only, within the same agent deadline, and never on timeout. The remaining deadline is passed as `HttpOptions.timeout` (ms). Reason: when the SDK's own retry is enabled, it also retries httpx timeouts and connect errors (VERIFIED §3.2), which §7.1 forbids.

D-007: `genai.Client(enterprise=True, project, location)` replaces `vertexai=True`. Reason: `enterprise` is the documented name in google-genai 2.26; `vertexai` is documented as its legacy alias (VERIFIED §2.1). The behaviour is the same.

D-008: The temperature is **not sent**. This deviates from §7.1, which says "Set temperature 0". Reason (VERIFIED §2.3): Google's docs say temperature is ignored by both configured models, and strongly recommend the default 1.0 for Gemini 3 because lower values may cause looping. Determinism for tests and the demo comes from mock fixtures (§14.2), not from temperature. Revisit if a model that honours temperature is configured.

D-009: Automatic function calling is disabled explicitly, and `max_output_tokens` is not set. Reason: we use no tools; the SDK otherwise logs an AFC warning on every call. Thinking tokens count against `max_output_tokens`, and a low cap cut off a live reply with `MAX_TOKENS` (VERIFIED §2.2).

D-010: How `judge_single` few-shot examples are built:
- utterance_judge examples A–F get `"facts":{"claims":[],"reason":"Facts not shown in this example."}`.
- fact_checker examples A and B become Examples G and H, with empty Job 1–4 fields (`utterance_type: product_talk`, switch `confidence: low`). The top-level `reason` is copied from the fact example.

Reason: `judge_single.md` asks for `"facts":{"claims":[],"reason":"..."}` but leaves the reason text open.
Known risk: examples C, D and F contain facts the model should mark `supported`, but they show empty claims. Evaluate this in the P2 split-vs-single report.

D-011: `CommentTriageOutput.condition_slots` is a pydantic model with the five fixed keys of `intents.json` (`skin_type`, `life_stage`, `condition`, `combined_with`, `time_of_day`). The JSON shape is unchanged; stored records (`QuestionGroup`) keep the spec's `dict[str, str|None]`. Reason: listing the keys in the schema tells the model exactly which keys to fill. §7.5 lists the keys in a comment only.

D-012: Prompt files are parsed as follows:
- **Required:** the version on the first heading, `## USER MESSAGE TEMPLATE` with a fenced block, and `## SYSTEM INSTRUCTION` (not for `judge_single`, which is built).
- **Optional:** `## EXAMPLES`.
- In the system instruction the EXAMPLES heading is written as `## EXAMPLES`; the developer note in parentheses is dropped.
- Headings inside code fences are ignored.

Reason: `broadcast_summary.md` has no EXAMPLES section. The parenthetical "(few-shot, include all of them in the prompt)" is a note to developers, not to the model.

D-013: Placeholder rendering rules:
- Names in the §7.1 string list are inserted as text; `None` becomes `null`.
- Every other placeholder must contain `_json`, which also covers `active_promo_json_or_null`, and is rendered as compact JSON (`ensure_ascii=False`).
- `</data` is escaped case-insensitively as `<\/data` in every value; JSON stays valid.
- Substitution is one pass, so a value that contains `{{...}}` is never expanded.

Reason: §7.1 rules, made precise for the one placeholder name that does not end in `_json`, and to stop injection through re-expansion (§3.4).

D-014: Modules added to the §4.2 layout:
- `app/clock.py`: testable clock.
- `app/ids.py`: ids.
- `app/context.py`: app wiring and the audit sink.
- `app/api/errors.py`: the `{error:{code,message}}` shape.
- `app/agents/base.py`: Agent protocol.

`/api/health` and `/api/catalog` live in `main.py`. Reason: §4.2 has no place for these concerns. Everything else follows the layout.

D-015: Id formats:
- ULIDs are generated in-house: 48-bit ms time plus 80 random bits, Crockford base32, no dependency.
- With `LLM_PROVIDER=mock`, ids are prefix + 6-digit counter per (session, prefix), e.g. `al_000001`. Session ids count per process.
- Agent-call ids use the prefix `call_`.

Reason: §6.2 asks for prefixed ULIDs and deterministic counters in mock mode, but lists no prefix for `AgentCall`.

D-016: `Session` gets these fields:
- `created_at`, used to find the latest demo session;
- the in-document state named in §6.3: `pre_covered`, `switch: SwitchState`, `cue: HostCue | None`.

Reason: §6.3 says these live "in session doc" without naming the fields. `/demo/current` (§11.1) needs a creation time.

D-017: Alias matching:
- Aliases match on word boundaries in lowercase text.
- The bare alias `cream` is ignored when the word `ampoule` also occurs.
- In `product_by_alias()`, the longest alias wins; a tie between different products returns `None`.
- `products_mentioned()` returns every product named, without the `cream` rule. It is the function to use where "exactly one product matches" (§8.8 step 6) or "names the other product" (§7.4 step 3).

Reason: §6.4 defines the rules for `product_by_alias` only. Comparison questions must still see both products.

D-018: Event sequence numbers:
- They are assigned in-process per session under a lock, then persisted, then fanned out.
- After a restart the counter continues from the highest stored `seq`.
- Event document ids are the zero-padded `seq` (`0000000001`).

Reason: §4.1 is a single process. VERIFIED §8 warns that a Firestore counter document incremented per event would contend during bursts. Re-check the document-id choice for Firestore in P6.

D-019: SSE details:
- `data:` carries only the payload (§11.2).
- The stream starts with `retry: 1000`.
- Each client has a queue of 5,000 events. A client that falls behind is disconnected and resumes from the store with `Last-Event-ID`.
- `Last-Event-ID` takes priority over `after_seq`.
- Heartbeat every 15 s.

Reason: this gives bounded memory per client and loses nothing, because every event is persisted.

D-020: The app starts as a factory: `uvicorn app.main:create_app --factory`.
- The data pack, prompts, store, bus and LLM client are built eagerly in `create_app`, so a broken pack or prompt file stops startup.
- Model warm-up runs as a background task at startup. Its result is shown in `/api/health`.

Reason: importing the module must not read `.env`, so tests use their own settings. §7.1 requires fail-fast prompt loading and warm-up without blocking liveness.

D-021: Memory store semantics:
- Documents are stored as JSON dicts and returned as fresh copies.
- Transactions run one at a time on a lock; their writes apply only if the block succeeds.
- Queries leave out documents that lack the `order_by` field, as Firestore does.

Reason: §6.3 requires the memory store to behave like Firestore.

D-022: Mock lookup key normalisation is lowercase, collapsed whitespace and trimmed. Mock outputs are validated with the same pydantic models as real ones. A request may carry a per-agent rule-based fallback. Reason: §7.1 defines the key but not the normalisation. Validating mock outputs keeps fixtures honest.

D-023: Agent calls made outside a session (Brief Agent, scripts) are written to a top-level `agent_calls` collection without an event. Reason: §7.1 requires an audit row for every call, but `agent.call` events belong to a session stream.

D-024: Tooling:
- Python 3.12 via `uv`; dependencies are minimum-pinned in `backend/pyproject.toml`.
- `aiohttp` must not be added. If it were importable, the genai async client would switch to it, silently retrying connection errors (VERIFIED §3.3).
- `httpx` is a direct dependency, because the provider maps httpx timeouts.

Reason: keeps the verified HTTP behaviour.

D-025: Modules of later phases (retriever, STT, agents, pipelines, remaining API routes, frontend) are created in their phase. `store/firestore.py` exists as a stub that raises `NotImplementedError` until P6. Reason: §0.1, one phase at a time; the layout fills in phase by phase.

## P1 Comment path (2026-10-01)

D-026: All delayed work goes through a keyed `Scheduler` (`app/scheduler.py`): escalation, publish windows, promo end, feed offsets and ticks. `AsyncScheduler` runs in real time. In tests, `ManualScheduler` with `ManualClock` fires timers only in `advance()`. A timer is removed from the registry before it runs, so cancelling never interrupts a half-applied change. Reason: §14.1 timer behaviour (5 s escalation, 2 s publish window, 20 s dwell, 10 s coalescing) must be testable deterministically.

D-027: Two modules are added to `pipelines/`:
- `runtime.py` (`SessionRuntime`, `Runtimes`, session creation);
- `demo_script.py` (host script parser).

One `asyncio.Lock` per session guards every state change, not only grouping. LLM calls never run while it is held: their results are applied afterwards under the lock, from fresh reads. Reason: timers, operator actions and both pipelines change the same documents. One lock is the simplest race-free rule.

D-028: Document additions:
- `Session.host_slots` (ordered `HostSlot{group_id, pinned, on_host_since}`) and `Session.active_promos` (all running promos). `active_promo_id` remains the price-changing one.
- `QuestionGroup.recalled_at`.

Reason: §8.11 needs an ordered slot list; §8.10 allows non-price promos in parallel; §8.13 recall blocks re-adding for 60 s.

D-029: Host slot order:
- Pinned groups come first, in pin order.
- Auto items keep their place; a newcomer takes the place of the item it replaces.
- On a score tie, the current holder stays.

Reason: "Questions stay in place while you speak" (§12.3.4).

D-030: The prefilter runs at intake before `comment.created` is emitted, so the event already carries `visibility`. `comment.hidden` follows for hidden comments. It is a pure function taking well under 1 ms, so the 300 ms target still holds. Reason: text hidden by the prefilter (links, phone numbers) never reaches host or viewer screens.

D-031: `logic/profanity.txt` is a short hand-written list of common English swear words plus a few Singlish vulgarities (knn, cb, lan jiao, pukimak). It is not taken from a third-party list. It deliberately excludes mild insults ("stupid", "annoying"), which the LLM classifies as `harassment`. Reason: required by §8.8.

D-032: Prefilter details:
- Emails and phone numbers are checked before links, so `jane@example.com` is `personal_info` and not `link`.
- Phone pattern: optional `+65`, first digit 6/8/9, eight digits, optional single spaces or hyphens between digits.
- Reaction-list matching lowercases and strips everything except letters, digits, spaces and `+`.

Reason: C19, C20 and B3 expect `personal_info`; "So pretty! 💜" must match "so pretty".

D-033: Analysis ids use the prefix `an_`. The `comment.analyzed` payload is `{comment, analysis}`. Reason: §6.2 lists no prefix for analyses; the operator desk needs both objects.

D-034: SSE and `/state` take `role=operator|host|viewer` (default `viewer`). For host and viewer:
- `agent.call` and `transcript.interim` are dropped;
- hidden comments are reduced to `{comment_id, visibility}`;
- analyses are removed.

Reason: §12 screens see different data. Without login (§2.2), this keeps personal data and debug output off the public screens.

D-035: Grouping rules:
- A group is open while its status is not `closed` or `rejected`.
- Joining does not merge slot values into the group.
- A new member of an already answered group gets the same reply text: added to the last reply within `REPLY_COALESCE_SEC`, otherwise a new reply. This applies to AI, host and brand answers, and makes no LLM call.

Reason: §8.9.1 and §8.9.3 cover joining and AUTO repeats; using the same rule for every answered group means no question is silently dropped.

D-036: The composer runs for every composable group, including OPERATOR-routed ones, so the operator gets a verified draft (S09). The outcomes:
- With `AUTO_ANSWER_ENABLED=false`, an AUTO group with a verified answer goes to `needs_review`.
- A composer timeout, error or invalid output sends the group to OPERATOR with `no_verified_answer`.

Reason: §7.6, §8.9.2 and the §7.2 failure column.

D-037: The feed endpoints (`/feed/*`) require `DEMO_TOOLS_ENABLED`. The `bursts` flag of `/feed/start` is accepted but unused; bursts are fired one by one. Rate limits apply to every comment source. Reason: the feed simulates viewers and is a demo tool; §11.1 does not define the `bursts` flag.

D-038: `promo_passage()` text:
- Label: "Time sale price (extra {pct}% off the live price)" for `time_sale` promos, otherwise the promo title.
- Then each product or set catalog name with its precomputed price, two decimals.
- So the set appears as "Hydra Barrier Cream + Deep Hydration Ampoule set" (catalog name), not "Cream + Ampoule set".

Reason: §8.10 says to build the text from `promo_prices` and catalog names.

D-039: Unhiding a comment re-runs triage; if triage says `hide` again, the operator's decision wins and the comment is treated as a reaction. Triage `hide` with no category becomes `spam`. Reason: §8.13 "Visible again; re-run triage". The operator is the human in control (§1.2).

D-040: Answers are counted per asker. An asker is `instant_answers` when answered from an existing verified answer (group or key cache), and `composed_answers` when they waited for a composer call. Reason: §8.16 defines both "for an asker".

D-041: `POST /comments` requires `VIEWER_INPUT_ENABLED` and returns 403 otherwise. The feed posts in process. Reason: §11.1 and §12.5. The recorded demo keeps chat read-only.

D-042: **Re-triage on a stale view.** Triage runs concurrently, so a paraphrase can be classified before the group of a near-simultaneous question exists. If grouping then finds no match but a compatible open group exists that the triage call did not see, triage runs once more with the current open groups. "Did not see" means the group was created while triage ran, or the output came from the triage cache. The LLM still decides; code only asks again. Reason: the live recording of B2 split the makeup questions into three groups; with re-triage the group has the expected 4 askers (§8.8 requires near-simultaneous paraphrases to join one group).

D-043: A `set_price` question with no resolved product is attributed to the on-air product (basis `context`). Reason: the model reasonably marks set questions as "both products" (`unknown`), which made them "unresolved". Both product sheets list the same set price, and S11 expects the set price question to be auto-answered with S$55.80.

D-044: A 504 `DEADLINE_EXCEEDED` from Vertex AI is treated as a timeout and not retried. Reason: the server enforces the deadline we send (`X-Server-Timeout`, VERIFIED §3.1), so it is a timeout (§7.1 "never retry on timeout").

D-045: **The local `.env` sets `LLM_QUALITY_THINKING=LOW`; the code default stays `MEDIUM` (§5).** Measured on 2026-10-01 with `gemini-3.8-flash`:
- At MEDIUM, the composer took 5.1–14.1 s with 484–1,823 thinking tokens on price questions. These carry 16–17 passages: search results plus Key facts.
- Twice it hit the 12 s `COMPOSER_TIMEOUT_MS`, which left the first price group without an answer.
- At LOW, the same questions took 2.3–3.4 s with equivalent cited answers (one 24.5 s outlier, which happened without any thinking, so it is service tail latency).

Reason: the ≤15 s first-answer target (§3.7) and the 12 s deadline. Revisit with the latency report in P5.

D-046: Comment eval scoring:
- Cases without an expected intent count as intent-correct when the kind is correct.
- Expected route = the labelled route, or the routing table applied to the labelled intent and product (the attributed product when none is labelled).
- Product attribution (§8.8 step 6) runs before routing, as in the pipeline.

Reason: §14.3 targets count over all 35 cases, but only 28 carry an intent label.
