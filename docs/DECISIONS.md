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

D-043: A `set_price` or `routine_order` question with no resolved product is attributed to the on-air product (basis `context`). Reason: the model reasonably marks these questions as "both products" (`unknown`), which made them "unresolved". Both product sheets carry the answer: the same set price, and "apply the ampoule first". S11 expects the time-sale set price question to be auto-answered with S$55.80. `routine_order` was added in P2 after a comment-eval run classified C26 as `routine_order` with both products named.

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

## P2 Utterance path (2026-10-01)

D-047: The provider does not set `HttpOptions.timeout`, so no `X-Server-Timeout` header is sent. The agent deadline is enforced by `asyncio.wait_for` alone, and cancelling it closes the HTTP request (VERIFIED §3.3). Reason: with the header, Vertex AI returned `504 DEADLINE_EXCEEDED` after about 1.4 s on a 2.5 s deadline for several judge calls. Without it, every call succeeded (VERIFIED §3.4).

D-048: A `contradicted` fact claim that cites a passage of the section "Approved on-air claims" is downgraded to `not_in_sources`. This is an extra check on top of §7.4. Reason: the fact checker sometimes "corrected" compliance sentences with the "Claims not approved" passage (U03, U05, U06). That is the judge's job, and the note would have been a wrong amber correction ("a wrong correction is worse than no correction", fact_checker.md).

D-049: `active_alerts_json` for the judge leaves out the provisional alerts of the transcript being judged. Reason: these alerts come from this very sentence and have not been shown to the host. Listing them invites the judge to "correct" them with the sentence that caused them. Earlier transcripts' alerts are always resolved by then, because steps 1–4 run one transcript at a time.

D-050: The per-session utterance order is kept with two chains of tasks instead of a queue and a worker:
- a "main" chain for steps 1–4;
- a "side" chain for steps 5–6.

Each task awaits the previous task of its chain, so the semantics of §8.2 are the same. Reason: no long-lived worker task; the manual test scheduler can wait for all work.

D-051: Event details:
- `judge.failed` is `{transcript_id, status, alert_ids}`.
- The second cue emits `segment.switch_counting` (cue 2/2) and then `segment.switch_pending`.
- A cancelled count (counting → idle) emits nothing.
- `segment.switch_cancelled` is `{reason}` with reason `speech`, `compliance_alert`, `operator` or `host`.
- `segment.missing_points` carries the missing ids and texts.
- `metrics.updated` is emitted every 5 ticks (5 s) while live.

Reason: §11.3 names the events; payloads follow what the screens show (§12.3.9, §12.4.4, §12.4.9).

D-052: Compliance alerts:
- There is at most one alert per (transcript, rule).
- A violation repeated while an alert of the same rule is active creates a new active alert (reflex skips the provisional step for that rule).
- Fact alerts use the id prefix `fx_`; only one per (product, field) is active.

Reason: §8.2 step 2 ("not already covered"), §8.4.2 ("1 of N"), §8.5 dedupe.

D-053: Publish decision: when condition 1 holds but only 4 (HIGH alert / violation) or 5 (contradicted fact) fails, nothing happens and the group stays on the host. Reason: §8.6 defines the "host answered on air · not posted" path only for failures of 2, 3 or 6. A host answer that carries a violation or a wrong fact must not be marked as answered.

D-054: Switch:
- While any HIGH alert is active, each judge output counts as a cancel, so counting resets and a pending switch is cancelled (§8.4.7).
- The cue window expiry is checked when the next judge output arrives; a cue after the window starts a new count.
- The operator may switch to any other run-sheet product.
- `POST /segments/cancel {by}` serves both the operator "Cancel switch" and the host Esc key.

Reason: §8.7.2 lists Esc and "Cancel switch" without an endpoint; expiry only matters at the next cue.

D-055: Undo moves groups back. A group goes back to the reopened product when one of its member comments was attributed by `context` to the undone product during the undone segment. Reason: the §8.7.2 Undo rule.

D-056: API additions:
- `/api/catalog` also returns rules (title, source_ref), passage labels, notice templates, intents and the policy PDF link.
- `GET /api/files/policy` serves the Appendix III PDF.
- `GET /alerts/{aid}/notice-template` prefills "Post notice".
- Demo tools add `POST /transcripts {text, scene}` (scene = mock scenario tag), `GET /api/demo/script` (parsed host script) and `POST /demo/simulate-overtime`.

Reason: §12.4.2, §12.4.3 and §12.6 need these, and v1 has no other way to read them.

D-057: `logic/summary_stats.py` (pure statistics, §8.14) is implemented in P2, because the P2 "done when" requires every §14.1 test, including summary stats. The recap agent and the summary page follow in P4.

D-058: Model outputs vary between runs: temperature cannot be pinned on these models (D-008). The eval targets met in each run, as recorded in `docs/eval/`. One comment-eval run had route 32/35 because C26 was classified `routine_order`; D-043 was extended for that. Fixtures are recorded from single runs and replayed deterministically.
D-059: Two event additions requested by the frontend:
- `group.updated` carries the group's current `answer` (draft or suggested answer). The client then needs no `/state` refetch when a composer finishes.
- A new `feed.updated` event (feed state) lets the Demo Console show and clear "B5 armed" from the stream.

Reason: §3.6 says screens are driven by events.

D-060: `JUDGE_MODE` stays `split`. Measured on 2026-10-01 (`docs/eval/2026-10-01-split.md`, `-single.md`):

| Mode | Runs | Judge p50 | Judge p95 | Targets |
|---|---|---|---|---|
| split | 30 | 1.37 s | 1.65 s | all met |
| single | 5 | 1.73 s | 2.06 s | facts 8/9 (U27 labelled `price` instead of `promo`) |

Reason: §14.3 keeps `split` unless `single` is at least as accurate on facts and compliance and faster on compliance. It is neither.

## P3 Screens (2026-10-01)

D-061: Studio accepts `?layout=all|host_viewer|host_operator` and `?recording=1` in the URL, so the screenshot and E2E drivers need no clicks. The Vite dev proxy target can be overridden with `API_TARGET`. Reason: deterministic captures (§15 P3) and parallel dev servers.
D-062: The judge's `say_instead` is rewritten so that a footnote `*` becomes the spoken qualifier "in our in-house test", using the same rule as the §8.4.3 fallback (`spoken_claim()`). Reason: the model copied approved claims with their `*` ("…24 hours.*"), which the host would read aloud. The prompt says to keep the qualifier.

D-063: Screenshots and browser checks use Playwright with the installed Microsoft Edge (`channel: "msedge"`, override with `PW_CHANNEL`). The `playwright` npm package is a dev dependency installed without a browser download. Reason: on the development machine, OS policy blocks starting executables from AppData (`spawn EPERM`, even outside the tool sandbox), so Playwright's bundled Chromium cannot run.

D-064: Frontend structure:
- Shared code is in `src/app` (api, types, SSE client, event-sourced store with pure reducers and selectors, theme, router) and `src/components`.
- Each screen has an entry file (`screens/Host.tsx`, …) plus a folder (`screens/host/`, `operator/`, `viewer/`) with its components, local selectors, CSS module and tests.
- The Host screen is designed at 1920×1080 and scaled by a measured factor (`--hs`), so the same layout fits 1280×720 and Studio panes. At 1280 wide the prompter text is about 29 px instead of the 33 px a pure `2.6vw` would give.

Reason: §12.3 targets 1920×1080 and "must also work at 1280×720" and in Studio panes. One scaled layout avoids layout shifts.

D-065: Operator alert cards wrap onto new rows instead of scrolling sideways. Reason: in the narrow Studio pane a card was cut off. Alerts must stay fully visible.

D-066: Known P3 limits, left for P5 polish:
1. The operator's transcript chips ("answered: …", covered points) are matched from the judge's `agent.call` input preview by transcript text.
2. "switch cue n/2" chips come only from live events, so they are missing after a page reload.
3. The host's green "Corrected" bar is triggered client-side when an alert turns corrected. A host page opened after a correction does not show it.
4. Host chat auto-scroll follows new rows only, not a reply added to an existing row.
5. The microphone controls are placeholders until P4.