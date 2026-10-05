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
## Review changes before P4 (2026-10-01)

D-067: **New config key `COMPOSER_THINKING`** (default `LOW`) sets the thinking level of the AnswerComposer only. `LLM_QUALITY_THINKING` stays `MEDIUM` for the Brief Agent and the Broadcast Summary. The key is in `config.py` and `.env.example`, and in `/api/health`. This replaces D-045, so the local `.env` is back to `LLM_QUALITY_THINKING=MEDIUM`. Reason: `docs/eval/composer-thinking.md` (25 questions × 3 runs per mode):
- LOW matched MEDIUM's verified-answer rate (72% vs 71% in run A; 77% vs 80% in run B, within noise);
- LOW was about 2.5× faster (p50 2.0 s vs 5.3 s);
- in the unloaded run, LOW was always within the 12 s deadline.

D-068: The composer also adds fixed passage sections for intents whose answer BM25 can miss:
- Key facts for origin, packaging, shelf life, texture and fragrance;
- Key ingredients for ingredients and ingredient amount;
- Cautions for allergy/sensitivity, pregnancy, medical condition and age.

This is on top of the §7.6 Key facts rule, never instead of it. Reason: "Where is it manufactured?" (Key facts "Made in: …") and "Does it sting?" (Cautions "…tingling…") failed 0/3 for lack of the passage. After the change they pass 2–3/3. Verify rates: LOW 72% → 77%, MEDIUM 71% → 80%.

## P4 Audio, setup, summary (2026-10-01)

D-069: Speech-to-Text:
- **Model and endpoint:** V2 `chirp_3` at `us-speech.googleapis.com`, with SHORT endpointing (about 0.5 s faster than STANDARD) and automatic punctuation.
- **Phrase hints:** the confirmed glossary's terms and spoken forms, at most 500.
- **`speech_end_at`:** the arrival time of the audio at the final result's end offset.
- **Interim results:** chirp_3 returns none (VERIFIED §4.10), so `transcript.interim` (throttled to 300 ms) only appears with other models.
- **WebSocket close codes:** with `STT_PROVIDER=mock` the audio WebSocket answers with an error status and closes with 4400. One microphone per session: a new connection closes the old one with 4409.

D-070: Microphone capture:
- An AudioWorklet (`public/pcm-worklet.js`) downsamples to 16 kHz mono with a box filter and sends 100 ms Int16 frames plus an RMS level.
- One mic client per page (`app/mic.ts`) is shared by the host screen (key `M`, dot green/amber/red/grey with a level bar) and the Demo Console (Start/Stop, last final).
- It reconnects with backoff (0.5 s to 5 s), except on 4400, 4404 and 4409.

D-071: STT stream restart: a soft restart at the first final result after 180 s of audio, a hard restart at 240 s, and a bridge of at most the last 5 s of unfinalized audio. Reason: tested live with scaled limits, the first version (hard limit only, full bridge) delayed finals after a restart by 3.7–4.2 s; with the soft restart and the cap they arrive in 0.9–1.9 s (VERIFIED §4.10).

D-072 (UI review 1): The host HIGH overlay has a solid frame on all four sides, `clamp(6px, 8px × scale, 8px)`, in the new token `--risk-strong` (dark `#E5484D`, light `#C4483B`). Contrast on `--risk-bg`:

| Text | Dark | Light |
|---|---|---|
| `--risk-text` | 10.27 | 6.62 |
| `--text` | 13.53 | 13.91 |
| `--text-2` | 7.33 | 5.12 |
| badge | 9.70 | 7.56 |
| frame (non-text, needs 3:1) | 4.00 | 4.24 |

All text meets AA.

D-073 (UI review 2): The question desk header count is the All tab count.

D-074 (UI review 3): One function, `deskStatus(group) → {label, tab}`, drives both the row chip and the tab, so every group is in exactly one tab and the tab counts sum to All.
- "AI answered" and "Answered" → Answered.
- "Host answered on air · not posted" and "Assign a product" → Needs review.
- Rejected → Closed.
- A "Composing" tab, not in §12.4.7, appears only while its count is above zero. Without it, composing groups would be in no tab and the counts would not sum.

D-075 (UI review 4): `set_price` groups and their comments show the set name from products.json **verbatim**: "Hydra Barrier Cream + Deep Hydration Ampoule set" (the set containing the group's product, else the first set). The review asked for "Cream + Ampoule set (set name from products.json)". products.json has no such short name, and labels are never invented (§0.3), so the products.json name is used. A short label would need a `short_name` on the set in the data pack.

D-076 (UI review 5): Viewer AI answers that cite a `PROMO#…` passage show "Source: active promotion". When a reply cites both a promo passage and a sheet passage, both sources are shown.

D-077 (UI review 6): Coalesced replies:
- The reply is shown once, under the first asker's comment.
- Every later asker's comment shows a compact "↳ Also answered: @{name}", in the viewer and the host chat.
- The "@Name" list under the reply was removed, because the per-asker lines replace it.

D-078 (UI review 7): Operator metric chips show "–" when there is no measured value (missing, null, NaN, or 0 of 0 answers). Real values appear in a Vertex run: `docs/screens/vertex-operator-metrics.png` ("Alert in 2.8s", "Judge p50 1.6s"). With the mock provider, measured latencies are about 0 and show as "0.0s".

D-079: Setup:
- **Confirm route:** `POST /setup/glossary/confirm` confirms both products in one step, as one glossary version, so S01 shows "Confirmed · version 1". `POST /setup/brief/{pid}/confirm` is kept as well.
- **Upload:** takes a raw `application/pdf` body with a `filename` query parameter, because `python-multipart` is not a dependency. Uploaded files go to `data/uploads/` (gitignored).
- **Index rebuild:** a PDF is re-indexed for its product only. `LocalRetriever.replace_product()` swaps that product's passages and bumps `doc_version`; the shipped `passages.jsonl` is never modified.
- **Parser:** handles the PDF's `\x7f` bullet glyph and wrapped table cells, and reproduces the shipped `passages.jsonl` exactly (76/76; `scripts/build_local_index.py --check`).

D-080: Setup state is frozen per session. At session creation, `glossary_version` and the confirmed prompter points are copied into the session (`Session.prompter_points`). The runtime passes them to the judge input, prompter coverage, the prompter view, the switch logic and missing-point texts. Prefetched passages are dropped when `doc_version` changes. Reason: §12.7 says accepted changes "apply from the next session"; running sessions are not affected.

D-081: Summary:
- `end()` starts `pipelines.summary.run_summary` in the background, as §8.1.4 describes.
- The pipeline stores `{status, stats, recap}` in `sessions/{sid}/summary/current` and emits `summary.ready`.
- If the recap fails or times out, the page shows the statistics without a recap.
- Recap sentences whose numbers are not in the statistics are dropped (§7.8).

## P5 Hardening (2026-10-01)

D-082: Rehearsals used synthetic voice. §14.5 asks for a real microphone and a human voice; no person could speak in this environment. The automated rehearsals (`frontend/e2e/rehearsal-voice.mjs`) stream Windows SAPI speech at real-time pace through the real audio WebSocket into real STT and real models, with a host page open in Edge. `docs/rehearsal.md` says this explicitly and lists the human rehearsal as still to do.

D-083: The E2E suite uses `@playwright/test` with the installed Edge (`channel: "msedge"`, D-063) against a backend with mock providers and recorded fixtures, so it is deterministic. Its base URL is `E2E_BASE`, and `E2E_START=1` starts the backend itself. Vitest is limited to `src/` (`vitest run --dir src`), so it does not collect the Playwright specs.

D-084: Known gap in the speed budget: "cached auto answer ≤ 1 s" (§3.7) is met only when the triage cache hits. Triage must run before the answer cache can be used, and it takes p50 about 1.3 s on `gemini-3.5-flash-lite` (MINIMAL). Measured comment → instant reply: median 1.3–2.0 s. See `docs/eval/latency.md`.
## After P5 review (2026-10-01)

D-085 (data pack change, approved by the reviewer; supersedes the label part of D-075): `data/products/products.json` set `set_cream_ampoule` gains `"short_name": "Cream + Ampoule set"`. This is the only change to the shipped data pack.
- **Model:** `SetOffer.short_name` is optional (`str | None`), so a pack without it still loads, and `/api/catalog` returns it.
- **Labels:** the operator desk product label and the comment-stream chip of `set_price` groups show `short_name`, falling back to `name` (`setLabel()` in `screens/operator/model.ts`).
- **Unchanged:** the full `name` stays in the promo passage text (`promo_passage`) and the agents' `set_offers_json` input, so recorded fixture quotes and prompts are unaffected. The viewer price card keeps its generic "Set S$…" line.

D-086: The recording-day backup is the fixture set of one clean Vertex run of the host script.
- **Clean check:** `record_demo_fixtures.py` now checks the whole run. It exits 1 with "RUN NOT CLEAN" if any agent call is not `ok` or the summary recap is not ready, because a failed call leaves no fixture and the mock replay would then mix runs.
- **Runs on 2026-10-01:** the first run was discarded (one composer call hit the 12 s deadline). The second run was clean: 85 calls (comment triage 39, composer 15, judge 15, fact checker 15, summary 1).
- **Refreshed after D-088:** one run was discarded (a comment triage call took 2.8 s against the 2.5 s deadline). The next was clean: 84 calls (comment triage 38, composer 15, judge 15, fact checker 15, summary 1). It is the current backup, with 11 stale composer outputs removed. The script's host lines all end with `.`, `?` or `!`, so injected lines are never merged.
- **Stale fixtures removed:** fixtures the clean run did not write were removed, except the eval-case fixtures (scenario = case id) and the S01 Brief Agent fixtures. That was 10 composer outputs and 1 summary from earlier runs; the backend tests and the E2E suite pass without them.
- **Replay check:** `tests/test_demo_script_api.py` (S02–S14 through the API, each scene's Expected state), `tests/test_bursts_api.py` (B1–B4), the full backend suite (299) and Playwright `npm run e2e` (S02–S14 on `/studio`, plus S01) pass on these fixtures. The scene screenshots were re-captured from them.

D-087: `verify_answer` and the composer are unchanged after the verify-failure review (`docs/eval/composer-verify-failures.md`).
- The review covered 150 eval calls and two full demo runs. Every rejection was the model's own empty, ungrounded answer to a question the sheet does not answer: eczema in children, wrinkles, teenagers, how long a bottle lasts, animal testing.
- No correct answer was rejected by a verify rule, so there was nothing of that kind to fix.
- `eval_composer.py --calls` writes every call (answer, citations, verify errors, passage ids) to JSON for this kind of review.

D-088: Split sentences are judged together (proposal B of `docs/eval/stt-fragments.md`, with the reviewer's rules).
- **When:** a final is merged with the previous final when the previous one arrived at most `UTTERANCE_MERGE_WINDOW_MS` (3500, new setting; 0 turns it off) earlier, measured on `received_at`, and does not end with `.`, `?` or `!` (closing quotes and brackets ignored).
  - A merged judgment covers at most 3 finals; a longer run starts a new judgment.
  - Nothing waits: every final is still processed as soon as it arrives.
- **What reads the joined text:** reflex, `UtteranceJudge` and `FactChecker` get "previous text + new text".
  - The judge's RECENT_TRANSCRIPT leaves out the fragments already inside the utterance.
  - The stored transcript keeps its own text and gains `merged_from_transcript_id` and `judged_text`. The operator transcript row shows "joined with previous".
- **The merged judgment replaces the fragment's judgment:**
  - **Switch cues:** if the fragment counted a cue and the merged judgment is a cue too, the cue keeps its count and moves to the merged final (`replaces_transcript_id` on `segment.switch_counting`), so the same cue never counts twice. If the merged judgment is not a cue, the fragment's cue is withdrawn: the count drops, and a pending switch is cancelled with reason `merged`. A cancel works as before.
  - **Host-answer linking:** with the same group and action, the fragment's effect is kept (no second post; a verbal link moves to the merged final). Otherwise the fragment's link is undone first: a post still in its cancel window is cancelled, and "confirmed" or "verbal" flags are cleared. Then the merged decision applies. A reply that is already published cannot be taken back, and no second reply is posted for that group.
  - **Prompter coverage only adds.** §6 says `covered_point_ids` is "monotonic, never removed", so a point covered by the fragment stays covered even if the merged judgment does not repeat it. This is a deliberate exception to "replaces". The operator cue's "done" state also stays.
- **Alerts:** a merged judgment never resolves an alert raised by its own fragments. Their compliance alerts ignore its `corrects_alert_ids`, and their fact notes are neither re-shown nor corrected by a "supported" reading. Only an operator dismiss or a host correction in a later utterance clears them. A rule already active from those fragments gets no second alert.
  - A violation repeated in a separate sentence still creates a new alert, as §8.4.1 and §8.4.2 ("1 of N") require.
- **Judge failure on a merged final:** §8.4.3 uses the reflex result on the joined text, so "…it does not" / "treat acne." is negated and cleared, not raised as unverified.
- **Not fixed by this:**
  - A claim in the first fragment is judged on its own before its continuation arrives. If the continuation negates or quotes it, the alert stays until the operator dismisses it (rule 4).
  - Speech-to-text mishearings such as "can't" → "can" (stt-fragments.md).
- **Tests:** `tests/test_utterance_merge.py`:
  - S08 split after "does not" → no active alert, also when the judge fails;
  - S07 split mid-claim → exactly one alert;
  - S12 split → `cue_count` rises once, and a cue the merged judgment does not repeat is withdrawn;
  - price split → one fact note;
  - fragment alerts not resolved by the merged judgment;
  - a split host answer posted once, or its pending post cancelled when the merged judgment disagrees.

## Mic rehearsal feedback (2026-10-01)

D-089: An apology alone no longer corrects a compliance alert.
- **Why:** in the first human rehearsal, the judge marked "Oh, I'm sorry." and "Let me correct that." as corrections.
- **Check:** `logic/corrections.py` now checks every compliance alert the judge lists in `corrects_alert_ids`. The correction counts only when the utterance:
  1. says an approved statement instead (the alert's `say_instead` or one of the product's approved claims): at least 60% of its content words heard, with spoken numbers, plural and tense forms and small speech-to-text slips tolerated; or
  2. retracts the claim: a policy negation cue plus at least half of the flagged span's content words ("your wrinkles won't disappear overnight").
- **Otherwise:** the alert stays active and escalates as usual, and the rejection is logged.
- **Unchanged:** the S07 script correction passes, and §8.4.5 (all alerts of the corrected sentence) still applies to accepted corrections.

D-090: Automatic product switch in two steps, replacing §8.7.2's "any two cues".
- **Step 1, arm:** a transition to the next product (not a quote or an answer, confidence medium or high) whose text names the product. The name check is a whole-word match of the full name or the short name ("ampoule").
- **Step 2, confirm:** a later utterance, within `SWITCH_CUE_WINDOW_SEC`, that states the next product's information (covers at least one of its prompter points). Quotes and answers to viewer questions do not count.
- **No longer switches:** a second bare transition, a name heard in passing, or information without a prior named transition.
- **Unchanged:** the 5 s countdown, Esc and Cancel, and the 60 s undo.
- **Merges (D-088):** a merged judgment is classified as if its fragment's cue had not been counted.

D-091: The host prompter is reference information, not a script read in order. It has no "next point": no arrow, no highlighted row, no auto-scroll, and no "Focus on your next point / Keep it natural" footer. It is a plain list: points already said keep a check and turn grey, and required points keep their tag (§12.3.3 changed).

D-092: The summary page starts with the AI recap (executive summary), above the totals and logs. Its label says "based on the numbers below" (§12.8 put it last, "above").

D-093: A PDF upload on /setup runs as a job, and the page shows its stages.
- **API:** `POST /setup/documents` returns 202 and the job; `GET /setup/documents/jobs/{id}` is polled every 300 ms.
- **Stages are the ones that really run in this mode:**
  - upload received → check (type, size, duplicate) → read the PDF text (pages) → match the product code → split into passages;
  - then locally "rebuild the local index", or in cloud mode "Store in Cloud Storage" and "Import to Vertex AI Search", which are shown as skipped because the import is manual in v1;
  - then ready.
- **Display:** each stage shows a status, a short detail and its time; a progress bar shows the share of finished stages. A failure marks its stage and shows the error.
- **Not yet built:** real Cloud Storage and Vertex AI Search stages come with P6 and fit the same job model (its long-running import is what the polling is for).

D-094: Glossary terms can be edited on /setup before confirming.
- **Editing:** term, kind and spoken forms (comma separated); a new term can be added ("Added on /setup").
- **Confirm:** only "Confirm glossary" saves. It collapses whitespace, drops empty or repeated spoken forms, and rejects an empty, overlong (more than 100 characters) or duplicate term.
- **Reload:** `GET /setup/glossary` returns `terms_by_product`. When the confirmation is newer than the Brief Agent run, the table starts from the confirmed (edited) terms, so a reload or a second confirmation does not silently drop edits.

D-095: Host screen layout (§12.3 changed).
- **Columns:** live chat, what hosts watch most, fills the right column; the prompter (top half) and the audience questions (bottom half) share the left one.
- **Sizes:** prompter points went from 28–44 px to 26 px, with tighter spacing and an inline "required" tag, and the question cards were tightened. A product's full point list and three questions fit without scrolling at 1920×1080.

D-096: The summary's compliance log and fact log are in one box under their own headings, with the same columns.
- **Columns:** time, what was said, rule or field, alert latency, corrected in, correction, unverified.
- **Fact field:** shows "stated → correct", and unverified is always "–".
- **Data:** fact rows gained `span`, `shown_at`, `speech_end_to_shown_ms`, `shown_to_corrected_ms` and `corrected_text`; the old fields stay.

D-097: "Export PDF" on the summary prints the page as a report: A4, light theme while printing, buttons hidden, cards and rows not split, table headers repeated. It opens the browser's print dialog ("Save as PDF"), and the document title "<session> - broadcast summary <date>" becomes the file name. A PDF library was not added. It is disabled while the recap is being written. "Export JSON" stays for data use.

D-098: Saying the "Say this instead" wording corrects the alert, even when the judge does not list it.
- **Why:** in the 2026-10-02 rehearsal the host said the exact wording shown on screen ("It helps relieve the feeling of dryness."), a few lines after the alert. The judge called it product talk, so the alert stayed on.
- **Cause 1:** the judge's ACTIVE_ALERTS input had no `say_instead`, so the judge could not tell that this was the shown wording.
- **Cause 2:** the judge sees only the last two lines, and chatter had pushed the violation out of them.
- **Fix:** ACTIVE_ALERTS now includes `say_instead`. Independently of the judge, an active compliance alert is corrected when an utterance says its replacement wording (at least 60% of the wording's content words, the same measure as D-089). This also works when the judge call fails.
- **Unchanged:** apologies, other approved claims and partial phrases still need the judge to list the alert and pass the D-089 check. Alerts raised by the fragments of a merged utterance stay protected (D-088).

D-099: Three agents read each host sentence in parallel (`JUDGE_MODE=split3`, the new default).
- **Agents:**
  - ComplianceJudge (`prompts/compliance_judge.md`): advertising-rule violations and corrections of active alerts;
  - ContextJudge (`prompts/context_judge.md`): answer linking, prompter points and cues, product switch;
  - FactChecker, unchanged.
  The two judges are cut from `utterance_judge.md` with the same wording, read the same input values, and get the same checks. `test_prompts.py` fails if the job texts drift apart.
- **Why:** measured on 39 eval cases × 20 runs (`docs/eval/agents-compare.md`):
  - accuracy is the same as one UtteranceJudge;
  - the compliance verdict, which drives the red alert, is ready about 0.3–0.4 s sooner: p50 1.20 s and p95 1.51 s, against 1.51–1.54 s and 1.83–1.93 s;
  - compliance timeouts fall to 2.8%, against 3.5–6.5%.
- **Production check** (`docs/eval/agents-split3-prod.md`, the production agents, 780 case runs on 2026-10-03):
  - every judge check is 100%;
  - compliance verdict p50 1.14 s, p95 1.39 s; context verdict p50 1.33 s, p95 1.54 s;
  - timeouts: compliance 1/780, context 3/780.
- **LLM router not adopted:** the alternative was an LLM router in front that picks the specialists. It was 0.5–0.8 s slower and used 3.13 calls per sentence, with no accuracy gain.
- **Order:**
  - each verdict is applied as soon as it arrives; the compliance verdict is applied first when both are in;
  - a new HIGH alert still resets switch counting and cancels a pending switch (§8.4.7), even if the context verdict came first;
  - the host-answer publish decision waits for both judges and the fact checker; if either judge failed, nothing is posted.
- **Failure:**
  - if the compliance judge fails, the Reflex fallback applies as before (§8.4.3, `judge.failed`);
  - if the context judge fails, only the prompter and the switch miss that sentence. This is logged, and not shown to the operator.
- **Cost:** three model calls per sentence instead of two (each judge prompt is shorter).
- **Rollback:** `JUDGE_MODE=split` (one UtteranceJudge); `single` stays.
- **Other changes:**
  - the judge p50 header chip uses `compliance_judge`;
  - the transcript chips read `context_judge`;
  - demo fixtures: the new `compliance_judge` and `context_judge` fixtures were recorded on Vertex AI, and the `utterance_judge` fixtures stay for `split`. The other agents are unchanged, so their fixtures stay from the last clean run.
  - None of the five recording runs on 2026-10-03 was clean. Each had one to three calls time out just past the deadline: comment triage, answer composer, fact checker, or context judge at 2.51 s. Compliance judge calls were 75/75 ok and context judge calls 72/75. The S12 "It's a watery gel…" context fixture is from the fourth run, the rest from the fifth. The demo replay test and the E2E suite pass.

D-100: The fact checker no longer leaves fact notes on compliance wording.
- **Problem:** 3–4% of non-fact sentences got a fact note, all of them compliance sentences:
  - "It whitens your skin in two weeks." → `test_result` 2 weeks → 4 weeks;
  - "prescription cream" → `other` → "cosmetic product".
  These passed the quote check (D-048) because the quoted passage was a real test result or product description, not the claims section.
- **Rules (code, `fact_checker.post_validate`):**
  - a contradiction on field `other` is downgraded to `not_in_sources`, since it has no value to compare;
  - a `test_result` contradiction stands only when the sentence cites a test (test, study, trial, clinical, participants, people, users, women, men, subjects, percent, %).
  The prompt is unchanged.
- **Measured** on the same saved model answers of three 780-run evaluations (`docs/eval/facts-leak-d100.md`, `eval_agents.py --revalidate`):
  - leaks went from 20/579, 23/560 and 19/551 to 0;
  - catching wrong facts and no note on right facts are unchanged.


D-101: Successive finals are judged concurrently; only state changes stay ordered.
- **Why:** a solo host talks continuously. Each final waited for the previous final's whole judging (`utterances.py` `_main` awaited the previous `_main`), so a slow context verdict (p95 about 1.9 s) delayed the next sentence's compliance verdict. Fact notes also waited behind the previous side task.
- **Now:**
  - preparation stays in transcript order: merge (D-088), store and emit `transcript.final`, reflex provisional alerts, judge input;
  - each prepared final starts its compliance, context and fact calls at once, without waiting for earlier verdicts;
  - compliance verdicts and fact notes are applied the moment they arrive (compliance first when both are in);
  - context verdicts (prompter, switch, answer linking) and host-answer publication stay in transcript order;
  - results carry the transcript sequence, source segment and switch generation, so a late result cannot switch products after a newer switch, bring back a corrected alert, or undo newer state; a late violation is still raised unless a later utterance already corrected it.
- **Tests:** `tests/test_utterance_concurrency.py` (late correction, merged fragments, switch and undo, timeouts, urgent facts, idempotence, all judge modes). `test_preparation_does_not_wait_for_the_previous_judge` now expects the second final's reflex alert before the first final's slow judge alert.
- **Rollback:** revert the `utterances.py` change; `JUDGE_MODE=split` and `single` keep working.
- Built by codex, reviewed and test-fixed by Claude (10/5).

D-102: Comment triage uses an adaptive micro-batch.
- **Why:** in a comment burst each comment made its own triage call (at most 8 at once), so later comments waited for a free slot and every comment paid for a full prompt. PLANNING 5.1.2 asks for "one waiting comment: now; several: one call".
- **Now:**
  - a comment that finds a free slot (`TRIAGE_CONCURRENCY`, default 8) is triaged alone with `comment_triage.md`, exactly as before;
  - comments that arrive while every slot is busy wait; the next free slot takes up to `TRIAGE_MAX_BATCH` (10) of them in one call (`comment_triage_batch.md`, deadline `TRIAGE_BATCH_TIMEOUT_MS` 5000);
  - there is no timer. The planning note's "up to 2 s" is not needed: under load the wait for a free slot is the collection window, and without load nothing waits (user choice, 10/5);
  - the batch prompt is built at load time from the single-comment rules and examples plus a short batch section, so the two never drift apart;
  - an item the model leaves out, or a failed batch call, is triaged again alone. Grouping, routing and answering still run per comment under the session lock, and the D-042 stale-group retry still applies;
  - under the mock provider a batched comment replays its recorded single-comment fixture, so demo bursts give the same outputs batched or not.
- **Tuning:** the three values are start values; tune them with burst tests on Vertex. Batched calls appear as agent `comment_triage_batch` in agent calls and metrics.
- **Tests:** `tests/test_triage_batch.py`.
- **Rollback:** `TRIAGE_MAX_BATCH=1` (every call is single again).

D-103: Fixes from the first unseen-sentence evaluation (10/5, `docs/eval/holdout-split3*.md`).
- **Set price notes (H046).** The fact checker caught a wrong time-sale set price 3/3, but `post_validate` dropped every claim whose `product_id` was not a product, and the set offer `set_cream_ampoule` is not one. A price, set price or promo claim may now name a set offer. It still stands only when its value equals the set's price under the active promo, or when it is backed by a quoted passage. The operator's price notice names the set. The fact prompt now asks for the `set_id` on set prices: in 2 of 6 runs the model put the set price on the cream, which stays downgraded. Test: `tests/test_facts.py` (set offers).
- **Tingling is not numbing (H076).** In 1 of 3 runs the compliance judge raised HIGH `ASEAN-3-SKIN-NUMBING` on approved wording (am-p5: "Sensitive skin may feel mild, temporary tingling. Patch test first."). The judge sees each rule's `description` but not the prompter points. Smallest fix: the rule's description in `data/policy/claim_rules.json` now says that mild, temporary tingling with patch-test advice is not this rule. The prompt and code are unchanged. Not chosen: adding prompter points to the compliance input (more tokens on every sentence, for one rule), or dropping violations in code without a reflex phrase (that breaks "judge the meaning, not keywords").
- **Read-outs name the question (U29).** The label is right: a read-out ("Someone is asking about oily skin, I'll get to that in a second.") must return the matched question with `is_answer = false`. The scorer stays strict. The answer-linking rule in `utterance_judge.md` and `context_judge.md` now says so. Example C's reason now says why its match is null: no open question is about the ampoule. Runtime is unaffected: a host answer is published only when `is_answer` is true. Cases to recheck on Vertex: U29, H073, H074, H077, S05 turn 1, S11 turn 1.
- Fact, compliance and context prompts changed, so the holdout and 39-case runs must be repeated before the numbers are compared.

D-104: A negated trigger phrase of the alert's own rule counts as a retraction (holdout sequence S08).
- **Why:** after "Use this tube and your dry skin condition will be permanently fixed for good.", the host said "Let me correct my earlier statement, cosmetic results are not permanent, regular daily use is needed." The compliance judge listed the correction 3/3, but the D-089 check rejected it: a retraction needed half of the flagged span's content words, and only "permanent" was repeated (1 of 6).
- **Now:** a listed correction also passes when the utterance contains one of the alert rule's `reflex_phrases` with a negation cue in the 4 words before it (the reflex scan's `negated` flag). A negated phrase of another rule, or the phrase without negation, does not count. Apologies alone still fail.
- **Not changed, for the planning session to decide:**
  - S01 run 1: the judge listed the correction one sentence early, on "It has a lightweight gel-cream texture that absorbs very quickly.", and D-089 accepted it because that sentence is an approved claim of the cream. The alert closed before the real retraction. Option: an approved claim other than `say_instead` counts only together with a negation or a correction cue.
  - S04 turn 2: the model output is right (no transition, no quote). The runtime does not confirm the switch on "This ampoule comes in a glass dropper bottle for targeted application.", because D-090 confirms only on a prompter point of the new product, and packaging is not one. The switch confirms on the next sentence (am-p1). The sequence scorer reads the runtime effect, while the 39-case scorer (U36) reads only the model output.
- **Tests:** `tests/test_corrections.py`.

D-105: A test number said without "in our in-house test" gets one yellow banner (PLANNING 5.1.3, user decision A).
- **Why:** all 6 false alerts of the v2 holdout run were in-house test numbers said without the qualifier. With no matching rule, the judge borrowed superlative or HIGH rules (ageing, physiological), so the host got a red overlay.
- **Rule:** `BRAND-TEST-QUALIFIER` in `data/policy/claim_rules.json`, MEDIUM only. Any number from a test or study (a percentage, "0 of 32", "24 hours") must come with "in our in-house test". Benefit wording without a number is exempt. The judge decides from the rule text and examples; no reflex phrases.
- **Code keeps it safe** (`logic/qualifier.py`, applied in `validate_compliance` and the utterance pipeline):
  - severity always comes from the rule (MEDIUM). Other rules are never demoted: a real ageing claim in the same sentence stays HIGH;
  - a sentence that already names our own test ("in-house", "in our 48-hour patch test") never gets this alert;
  - "Say this instead" is always approved wording: `Product.qualified_results` in `data/products/products.json` holds one sentence per in-house result, with the sheet's number, timing and qualifier. The sentence is chosen by matching numbers first, then the product on air, then words. Without a match it is empty, and the host card says "Say the result with 'in our in-house test'." The model's own wording is never used;
  - the same result alerts once per product segment, even after a correction (fewer yellow banners, interview #2).
- **Wrong number too (H052):** the alert and the fact note stay separate in events, logs and evaluation. On the host screen, a test-qualifier banner and a fact note on the same sentence show as one card with "○ +45% (not +70%)". The fact note joins the card when the fact checker finishes; the first card is never delayed.
- **To review:** the nine approved sentences in `qualified_results` were written from section 5 of the product sheets and need the user's check. Uploaded products (setup) have no `qualified_results` yet, so their banners show the generic line.
- **Tests:** `tests/test_qualifier.py`, `frontend/src/screens/host/host.test.tsx` (test qualifier).

D-106: Compliance alerts take the prompter's product box; the box is laid out like the earlier prototype (user, 10/5).
- **Why:** on the demo, the user found the alerts too far from YOUR PROMPTER, so they did not look urgent. The host's eyes are already on the product information.
- **Product box** (`Prompter.tsx`, fixed size: the left column's top half):
  - three labeled columns: Price & offers (the live or time-sale price is the biggest text; list and set price below), Ingredients (up to 4 amounts from `key_facts` with a percentage, big number and name), Points to say (the prompter points; the first required point not said yet is bigger);
  - two blocks below: Caution and Avoid saying ("✕ wording → approved claim"). They come from new `products.json` fields `cautions` and `avoid_saying`; each replacement is an approved claim word for word;
  - facts the host already said turn grey (points by `covered_point_ids`; an ingredient when a said point names it). The price never turns grey. A price point is listed only when it is required.
- **Alerts:** an active HIGH (red) or MEDIUM (yellow) alert replaces the product box's content: badge, "Heard: ..." small, "Say this instead." and the replacement as the biggest text. Several alerts stack in the box, HIGH first. The test-qualifier and fact merge (D-105) shows there too. On correction, the green "Corrected" fills the box for `CORRECTED_TOAST_MS`, then the product information returns. The full-screen overlay and the separate MEDIUM banner are gone; fact notes and the switch banner stay in the banner strip.
- **Unchanged:** alerts render on arrival (the 3 s path), the render acknowledgement, and the AI PD card hidden during a HIGH alert.
- **Not changed, to decide:** the AI PD card above the prompter and the banner strip still push the prompter down when they appear.

D-107: Fact notes join the prompter box; the box never moves or clips; no "say this point" card (user, 10/5).
- **Fact notes:** wrong product information is as urgent as a compliance alert (3 s target), so a fact note takes the prompter's product box too: "Heard: ✕ wrong value" small, "Say this instead." and the right value as the biggest text, then the source. Order in the box: HIGH, fact notes, MEDIUM. When the host restates the right value, the green "Corrected" fills the box, then the product information returns. The top banner strip is gone.
- **Why the user's "seventy percent" sentence showed a separate fact note (47de8e5 on :8000):** the first "Hydration goes up 70% after one use." produced both the test-qualifier alert and the fact note (one merged card). The second identical sentence got the qualifier verdict from the compliance judge again, but D-105's "the same result alerts once per product segment" dropped it, because that result had already been alerted (and corrected) in this segment. Only the fact note remained. Checked in the demo session's agent calls and alerts.
- **The box never moves:** the cue strip, the switch banner and the AI PD card now come and go above the audience questions (bottom of the left column), not above the prompter.
- **Never clipped** (the prototype's fitSlot): when the box content is taller than the box, it shrinks step by step down to 80% zoom; if it still does not fit, the card grows downward (its top stays; the questions get less room). Checked at 1920×1080 and 1366×768 with the cream and with HIGH + fact + MEDIUM stacked.
- **AI PD without "say this point" (agreed with codex and agy):** the prompter's highlighted next required point is the talking-point cue, so `cover_point` cards are no longer offered (neither for missing required points nor during a pause). In the prompter box instead:
  - a status line, e.g. "2 required points left · 0:30" (time left in the planned segment; "+0:15 over" after it);
  - from 80% of the planned time, the next unsaid required point is emphasised once (one short animation, none with reduced motion; no repeat on pauses).
  From 80% of the planned time, the switch or wrap-up card is offered even with required points missing, and then names them verbatim: "Before switching: <points>, then introduce <next product>." It ranks above viewer questions while points are missing, and its text is refreshed when one is said. PD cards now cover only viewer questions with verified answers, promos, and switch or wrap-up. Coverage tracking and the D-090 switch rules are unchanged: a switch card never switches by itself (test).
- **Demo Console:** a drag handle (and arrow keys) resizes the open console; the height is remembered per browser (`ls.console.height`, storage errors ignored). The bar still collapses it.
- **Tests:** `tests/test_pd.py`; `frontend/src/screens/host/host.test.tsx`; `frontend/src/screens/screens.test.tsx`; e2e expects the new fact label.

D-108: A claim repeated after its correction alerts again (user, 10/5: "계속 띄워야지").
- D-105's "the same test result alerts once per product segment" is replaced: a test-qualifier alert is skipped only while an alert with the same approved wording is still provisional or active (no second card for the same claim). After a correction, or after the alert ended, a repeat is a new alert with the same box rules.
- Fact notes and the other compliance rules already worked this way (a new note once the earlier one is corrected); tests now cover both.
- **Tests:** `tests/test_qualifier.py` (wrong, correct, wrong again: second alert, for the qualifier and for a fact note).

D-110: A host's spoken answer is auto-posted only when it clearly matches the verified draft (user, 10/5).
- **Rule (all must hold, else nothing is posted; the card stays and "Confirm and post" still works):** the utterance answers the offered question with a statement (`utterance_type` "answer", `is_answer`); the context judge finds it consistent with the draft; the answer is verified, unpublished, with no active HIGH alert, no violation and no contradicted fact (unchanged, §8.6).
- **New code checks** (`logic/publish.py`, on top of the judge):
  - every number the host says (spoken forms normalised: "fifty mils", "thirty-six dollars", "four percent") must be in the draft, or in another offered draft when the host answers two questions at once. Saying less than the draft is fine, because the posted text is the draft;
  - hedges and take-backs never post ("I think", "maybe", "not sure", "don't quote me", "let me check", "wait, no");
  - the post is bound to the answer shown with the question when the sentence was judged and to the current promo and document state (`answer.cache_key`); a changed or stale answer is not posted. Posting stays deduplicated (unpublished check, idempotency key).
  - "Host confirmed the AI answer" stays a mark only and still follows the judge's consistency.
- **Prompt:** the answer-linking rule in `utterance_judge.md` and `context_judge.md` now says that a question back, a quote or a hypothetical is not an answer, and that consistency means the same direction and numbers, with no added claim, caveat, condition, restriction or uncertainty.
- **Eval:** `scripts/eval_verbal_post.py` on `data/eval/verbal_post_cases.jsonl` (40 cases, 20 near-misses) runs the production agents and the real decision, and reports false posts (target 0) and missed posts separately. Unit tests check that the code layer never blocks an expected post and always blocks the wrong-number, hedge and retraction cases.

D-109: Settings gear with theme and screen language (user, 10/5).
- The light/dark toggle on the host and operator screens is replaced by a gear (`SettingsButton`): theme (light, dark, system) and screen language (English, 한국어). The language is one choice per browser (`ls.lang`, storage errors ignored) shared by the host and operator screens, and later setup and summary. The viewer screen stays English (it stands in for the platform chat). In the Studio panes the Studio controls the theme, so the gear is hidden there.
- Labels only: headers, buttons, badges, status lines, empty states, tooltips, intent and field labels. What the host says on air (say-instead lines, suggested answers, product facts, promo text), comments, quick replies, cue presets, rule titles and policy references stay in the broadcast language. English strings are the keys (`src/app/i18n.ts`); Korean is in `i18n.ko.ts` and `i18n.ko.operator.ts` (about 290 entries, to be reviewed by the user). "Dismiss" is "닫기" on both screens.
- Card text written by the backend (for example the AI PD card's detail line) is still English.
- **Tests:** `src/app/i18n.test.ts`; Korean rendering and the gear in `host.test.tsx`; a Korean header in `operator.test.tsx`.

D-111: Show mode, solo or team, chosen when a session is created (default solo).
- Stored on the session (`show_mode`); `POST /sessions {"show_mode": "team"}`; a demo reset keeps the mode. The Demo Console shows the current mode and picks the mode of the next "New demo session".
- Used by the unresolved-question list (team: the operator follows up; solo: the list stays for after the show, and a no-evidence question reaches the host only when 3+ viewers ask it).

D-112: A plain answer is recognised without a read-out; the correct pregnancy answer is not a vulnerable-group claim (user, 10/5: "질문 읽고 답 읽는 구조가 아니라 그냥 답만 해도 잘 인식해야지").
- **Why:** the first verbal-post run on Vertex (`docs/eval/verbal-post.md`, 82af749) had 0 false posts but 31 of 60 missed posts; 28 of them were sentences the judge did not link because the host answered without reading the question first.
- **Prompt** (`utterance_judge.md` and `context_judge.md`, same wording): a sentence that states the answer to ANY open question answers it, with no read-out or "yes" needed; `utterance_type` is then `answer`. When two open questions fit, the one marked `on_screen` wins.
- **Input:** OPEN_QUESTIONS marks the question whose card the host sees now (`on_screen`: the active AI PD answer card, else the first question slot). The eval uses the case's `shown_group_id`.
- **Unchanged:** every D-110 code check (numbers in the shown or another offered draft, hedges and take-backs, binding to the shown answer and the promo/doc state, no violation, `utterance_type` "answer"). The posted text is still the verified draft.
- **Pregnancy answer (V08):** in 1 of 3 runs the compliance judge raised HIGH `ASEAN-2D-VULNERABLE` on the correct answer ("it hasn't been specifically tested for that, so please ask your doctor first"). As with D-103, the rule's description now says that this approved answer is not the rule.

D-113: Every question card goes to the host, one at a time, paced by the AI PD (user, 10/5; UI reviewed with GPT and Gemini, "추천대로").
- **Routing:** no operator routing by sensitivity: sensitive questions (pregnancy, allergy, conditions, ...) go to the host with their verified draft. A question whose product is unclear goes to the host as "Which product?". General questions (shipping, returns, payment, ...) keep their intent route for now (step F revisits them).
- **Host screen:** one fixed AI PD card slot under YOUR PROMPTER is the only place an answer appears: the question (about 22px) and how many asked, above the answer (about 30px). AUDIENCE QUESTIONS is a compact waiting list (`HOST_TOP_N` 6): question, asker count and state (Drafting… / Which product? / Read out / Ready / No answer yet / On your card), never the answer text; "For you" and "TOP N" are gone. Key Q (or `POST /pd/pull`) takes the top waiting question at once.
- **Pacing (AI PD):** a question card (answer, read-out or "which product?") is released only at a pause (8 s without a final, or before the host first speaks), at least 45 s after the previous question card started (`Q_GAP_MS`), and only with a verified draft or a "which product?" line; a drafting question waits in the list. An active question card is not replaced by another question; it ends when the host answers, reads it out or names it (the context judge links the sentence), or dismisses it.
- **Read-out card:** an AI-answered question with 3 or more askers (`HOST_REPEAT_THRESHOLD` 3, was 5) the host has not mentioned: "N people asked: …" above the verified answer.
- **Shout-out card:** purchase, first-time and compliment reactions (keyword rules on the reaction path, no LLM call), read with a fixed template and the viewer's name. Only at a pause, never while a question waits, at least 30 s apart; they never delay a question.
- **Team show:** the operator's push skips the time gap (still at a pause, still verified, still under a red alert's priority) and replaces the current question card; the operator's row shows "On the host's card" when it is on screen.
- **Tests:** `tests/test_pd.py` (gap, pause, push, pull, read-out, which product, shout-out, a paced card on the runtime), routing and queue tests, host UI tests, e2e S04/S09/B5.

D-114: Product talk that answers an open question is an answer (user, 10/5: our own functional set must pass 100%).
- **Why:** on c6031d9 (D-112) 6 of 78 expected posts were missed. In every miss the judge labelled the sentence `product_talk` because it also stated a product fact or a prompter point (an ingredient amount, "no added fragrance") and so did not link it to the open question asking for that fact.
- **Prompt** (both judges, same wording, a general rule, no case sentences): one sentence can cover a prompter point AND answer a question; `product_talk` only when the sentence answers none of the open questions; check every open question first.
- **Scorer:** a post to any group in `matched_group` + `also_ok_groups` is correct (one sentence may answer two questions). Re-scoring the saved c6031d9 outputs: 0 false posts, 6 missed; the prompt change needs a new Vertex run.

D-115: Host screen fixes after the GPT/Gemini review of 62cff40 (user approved).
- **Corrected:** no full green box any more. A compact green "Corrected" line sits at the top of the prompter box and the product information shows at once below it, for compliance and fact corrections alike.
- **Fact card:** keeps the box; the right value is the hero (38px), "Heard" and the source line are 16px, aligned like the red alert.
- **Status line:** one reserved 64px line at the bottom of the prompter shows, in this order, the switch countdown with "Cancel switch (Esc)", the PD's cue, or "N required points left · m:ss". Nothing outside the prompter appears or disappears, so the AI PD card slot and the waiting list never move.
- **Red alert:** unchanged.
- **Fewer repeated badges:** no "REQUIRED" on every point (the counter, the status line and the checkmarks carry it); in the host chat, later askers of one coalesced reply fold into one note under the first asker ("Also answered: @A, @B").
- **Tests:** `host.test.tsx` (compact Corrected with points visible, switch in the status line, no REQUIRED tags, chat folding).

D-116: Verbal-post fixes from the hidden set (41814a3: public 3/78 missed, hidden 11/66 missed, 0 false posts; bar is 100%).
- **Spoken decimals:** "zero point two percent", "five point five" now normalise to 0.2 and 5.5 before the number check (`publish.spoken_numbers`). Caused HV06, HV13 and HV22 (9 misses).
- **No test qualifier on ingredient amounts, prices, volumes or pH:** in 2 of 3 runs the compliance judge raised `BRAND-TEST-QUALIFIER` (MEDIUM, on air) on "The cream has five percent panthenol." The rule text now says that only results of a test or study need the qualifier. Code guard: a qualifier verdict whose sentence matches none of the product's in-house results (`qualified_results`, by numbers or words) is dropped. Not chosen: gating on the fact checker's field label, because the fact checker runs in parallel and often finishes after the alert is already shown. This also replaces D-105's "no match: generic line".
- **Implicit answers (V45):** both judge prompts say that giving the facts or advice of a suggested answer answers it, even without "yes" or naming the question.
- **Scorer:** `--cases <file>` runs any case file in `data/eval` (e.g. `verbal_post_holdout.jsonl`). Unit tests now run the code checks on the public and hidden cases.

D-117: Fixes from the GPT code review of c6031d9, each proven first by a failing test.
- **B1, one correction cleared every alert of the same sentence** (`logic/alerts.apply_corrections`, §8.4.5): with two claims in one sentence, retracting one also cleared the other, bypassing the D-089 check. Now only the alerts that passed the check (or whose replacement wording was said, D-098) are corrected. Test: `test_corrections.py` (two rules, one retracted, the other stays active); `test_alerts.py` updated.
- **B2, word overlap counted negated or incomplete replacement wording as a correction** (`logic/corrections.py`): "It does not keep skin hydrated for 24 hours" matched the replacement by word overlap. An approved statement now counts only when one clause has CLAIM_MIN of its words, every number it has, no negation (unless the claim itself is negative), and its "in our in-house test" qualifier when it has one. The late-alert reconciliation (no judge decision) now accepts only the alert's own replacement or an explicit retraction, not any approved claim. Tests: `test_corrections.py`; `test_utterance_merge.py` now corrects with the full approved claim.
- **B3, fact notes keyed by (product, field) only** (`logic/facts.py`, utterance sequencing): "squalane is 3%" (right) cleared a "panthenol is 10%" note, and two wrong ingredient amounts shared one note. Notes and their ordering are now keyed by subject (product, field, source passage). A supported claim corrects the note of the same passage; without a passage, the note whose right value the host now states, or the only note of that field when no number is said. A passage-less claim also orders the whole field, so a newer correction still prevents an older note that arrives late. Test: `test_facts.py` (two ingredients).
- **B4, a pending host answer was posted without a recheck** (`post_host_answer_locked`): if, in the 2 s cancel window, the question was closed (a time sale closes price questions), answered, or got a new answer, or the promo or document state changed, the old reply was still posted. The post is now bound to the answer id and the answer key (promo and document state) at the time of speaking; on any change it is cancelled (`message.cancelled`) instead of published. Test: `test_publish.py` (closed, new answer).
- **B6, the voice rehearsal could not prove a missed alert** (`frontend/e2e/rehearsal-voice.mjs`): the driver counted finals after speaking, kept only the last final and looked for alerts on that final only. It now captures the final count before playback, collects every final of the line until 1.5 s pass without a new one, takes the first rendered alert raised by any of them (and which final raised it), and records each final's compliance verdict and alerts. The "pregnancy line had no alert" finding must be re-run with this driver.
- **B7, a claim split by STT punctuation** ("It's totally safe." / "For pregnant women."): not merged, because merging every short final would swallow fast short corrections ("Sorry, thirty-six dollars.") into the wrong sentence, and D-088 never lets a merged utterance correct its own fragments (18 tests failed on the trial). Instead the compliance job (same wording in `utterance_judge.md` and `compliance_judge.md`) now says: when UTTERANCE completes a claim begun in the last line of RECENT_TRANSCRIPT, judge the completed claim, with the span from UTTERANCE, and do not list again a claim the earlier line made alone. The judge already receives the last two finals. The adversarial "split" cases measure it.
- **B5, a draft for the old product could land on a reassigned question** (`comments.assign_product`, `compose_for_group`): a question still being drafted kept its "composing" state when the operator assigned another product, and the finished cream draft was applied to the ampoule question. Reassignment now always resets the question, and a finished draft is applied only when its key still equals the question's current answer key (product, promo, document). On a mismatch the question is drafted again for the current state, so a promo or document change during drafting can neither apply a stale draft nor leave the question stuck. Tests: `test_comment_pipeline.py` (reassignment, promo change while drafting).
- **B8, swapped values passed verification** (`logic/verify.py`): rule 4 only checked that each number of a draft appears in some cited quote, so "3% panthenol and 5% squalane" passed against "Panthenol: 5%" and "Squalane: 3%". New rule 6: the sheet's "Label: value" facts give subjects ("panthenol" = 5); a number in the draft whose nearest such subject (within 3 words) has another value in the quotes fails. Label words with several values ("price" for live and list price) and product names are not subjects, so normal answers are unaffected (all recorded demo drafts still verify). Tests: `test_verify.py`.
- **B9, work under the shared lock grew with the session** (`runtime.recompute_host_queue_locked`, utterance preparation): every queue refresh rescored and saved every group ever created, and every final loaded all transcripts to use the last two. Now answered, rejected and closed groups are skipped (unless one still holds a host slot), a group is saved only when its slot or score changed, and preparation reads a bounded tail of transcripts. Lock wait is not measured separately yet; it belongs with the planned Cloud Trace work. Test: `test_host_queue.py` (30 old groups are neither rescored nor saved).

D-118: The next final continuing the same claim adds no second card (voice rehearsal on 23627bd).
- **Why:** "The ampoule treats acne." / "So you will never break out again." came back as two finals and raised ASEAN-3-SKIN-ACNE twice: two red cards ("1 of 2"), and a correction of the first claim did not clear the second card because its span was different.
- **Now:** when the previous final (in transcript order, same segment, inside `UTTERANCE_MERGE_WINDOW_MS`) already has an active or provisional alert of a rule, the next final's verdict for that rule adds no new alert. Separate sentences further apart keep §8.4.2 (a repeat is a new alert), and a repeat after a correction still alerts (D-108). In-memory check only; the 3 s alert path is unchanged.
- **Tests:** `test_alerts.py` (adjacent continuation: one card; repeat 5 s later: second card).

D-119: Settings gear on the host screen: reading size and microphone input (user, 10/5; nothing else is added).
- **Reading size** 100 / 125 / 150% multiplies the host screen's scale (`--hs`); stored per browser (`ls.host.size`). The prompter box still fits by shrinking or growing (D-107).
- **Microphone input:** a list of the audio inputs (labels appear after the browser has granted access once) and "System default"; stored per browser (`ls.mic.device`). A running microphone switches to the chosen input at once.
- Both can be set before the show and changed during it; storage errors are ignored. No thresholds, timers or pacing in Settings.
- **Tests:** `host.test.tsx` (scale × 1.5 remembered; device list and choice).

D-120: Operator question desk (S09 review, user approved).
- The desk list scrolls inside its own bounds; the comment stream below keeps at least 200px.
- A collapsed row shows the proposed reply in one line (or "Drafting a reply…" / "No AI draft for this question.") and the next action as a button (Approve, Post suggested answer or Push to host), so the operator does not have to open each row. The status chip stays.
- Header latency chips appear only once a real latency is measured; mock runs no longer show "0.0s".
- **Tests:** `operator.test.tsx`.

D-121: Fixes from the adversarial eval on 23627bd (tune 90.5%, sealed 92.5% detection; pass line 95%), general rules only.
- **An ingredient the product does not contain** ("4% niacinamide" on the cream): the fact checker may now return field `ingredient`, `correct_value` "not in this product", no passage. Code shows it only after checking that none of the product's sheet passages name that ingredient (`fact_checker._absent_from_sheet`); otherwise it is downgraded as before. The host card shows "○ not in this product".
- **pH:** new fact field `ph` (it was `other`, which never makes a note, D-100); a value or range outside the sheet's is contradicted. Display label "pH".
- **Container type:** the prompt now says that the container (jar, tube, pump, dropper bottle) is a packaging fact.
- **A vouched quote is the host's own claim:** compliance job (same wording in both judge prompts): repeating someone's claim and then agreeing with it or vouching for it ("and I believe her", "no exaggeration") is not a quote.
- **Tests:** `test_facts.py` (absent ingredient only when the sheet never names it; pH note). The prompt rules are measured by the adversarial rerun.

D-122: Viewer screen (S11 review, user approved).
- The time-sale pop-up over the video is now a compact banner right above the price strip ("TIME SALE · text · countdown"); it still shows for 4 s when a sale starts and the chip in the strip stays. The product/video area keeps its size.
- Answer cards use less padding; "Source: …" expands the cited quotes inline under the reply instead of opening a sheet.
- **Tests:** `viewer.test.tsx` (inline source details); e2e S11 unchanged (same test id).

D-123: Fixes from the adversarial rerun on 1f8b8d3 (tune 99.2% detection; sealed round 1 had 1 false HIGH and 2.5% false alerts).
- **Approved wording is never a violation** (AV037: ASEAN-3-SKIN-ACNE, HIGH, with the span "29 of 32 participants said their skin felt less dry after 2 weeks", an approved in-house result): `validate_compliance` drops a violation whose span is the on-air product's approved wording (an approved claim, an approved in-house result or a prompter point: at least 80% of the span's content words and every number of it). The test-qualifier rule is exempt (an unqualified approved number still needs the qualifier). A code guard, because the judge's reason was not saved; the adversarial harness now saves every judge and fact output with its reason (`calls`).
- **A less specific wording is not a wrong fact** (AV117: "a 50 mL tube" got a packaging note although the cream is an "Airless pump tube"): for packaging, texture, fragrance and origin, a contradiction whose stated words are all part of the sheet's value is downgraded.
- **Scorer:** the expected right value is compared only with the alert of the expected field (a correct volume note plus a correct packaging note on the same line is not a wrong text). Re-scored tune outputs: PASS (99.2%, 0 wrong HIGH, 0% false alerts, 0 wrong texts).
- Not changed: AV083 (1 miss in 1 run, a negated claim followed by the same claim affirmed).
- **Tests:** `test_qualifier.py` (approved span), `test_facts.py` (less specific container).

D-124: Draft-verifier gate: verify_answer alone lets every seeded bad draft through (tune half, 3722a95).
- `scripts/eval_draft_verifier.py --cases <file>` runs the deterministic `verify_answer` on seeded drafts: **30 of 30 bad drafts pass** (polarity flips, dropped qualifiers, scope creep, invented suitability or policies, wrong pH in words, wrong packaging, wrong product's facts, off-topic answers). So the LLM draft verifier (proof-plan item 3) is needed.
- The gate also caught a false block in D-117 B8: 3 of 30 good drafts were blocked because label words next to another number ("Sodium hyaluronate (3 molecular weights): 1%", "48-hour patch test: 0 of 30") were taken as subjects. Such words are no longer subjects. Now 0 of 30 good drafts are blocked; the swapped-value tests still fail as they should. Test: `test_verify.py` (all good gate drafts verify).

D-125: Model Armor screens viewer comments before triage (code only; off until a template exists).
- **Order:** deterministic prefilter, then Model Armor `sanitizeUserPrompt` on every remaining comment, then triage. An answer-cache hit does not skip Armor (a cached answer is still an answer to the injected text).
- **Blocked** (template filters: prompt injection and jailbreak at MEDIUM_AND_ABOVE, malicious URLs, RAI at HIGH): no LLM call, the comment is hidden from chat (`hide_category` `armor_blocked`). A team show lists it in the operator's hidden list; a solo show only counts it (`metrics.armor.blocked`). Never a host card. Unhide brings it back to chat as a reaction and still sends it to no LLM.
- **Unscreened** (Armor error or slower than `MODEL_ARMOR_TIMEOUT_MS`, 500 ms): the comment stays in chat as a plain comment but is never triaged, answered or carded (fail closed for the AI, fail open for chat). Counted in `metrics.armor.unscreened`; the operator sees an "Unscreened" chip.
- Settings: `MODEL_ARMOR_ENABLED` (false), `MODEL_ARMOR_LOCATION` (us-central1, next to the service), `MODEL_ARMOR_TEMPLATE`. The service account needs `roles/modelarmor.user`. The template is not created yet (needs the user's approval).
- **Tests:** `test_comment_pipeline.py` (blocked never reaches an LLM and unhide does not either, cache hits are screened, error and timeout leave the comment unscreened).

D-126: LLM draft verifier after verify_answer (proof-plan item 3), plus a code rule for in-house test numbers.
- **DraftVerifier** (`prompts/draft_verifier.md`, `LLM_FAST_MODEL`, MINIMAL): reads the question, the draft and the full text of the passages it cites, and fails a draft for a statement not stated in them, a changed meaning, an overstated result or safety statement, a weakened caution, or a reply that does not answer the question. It runs only when the code checks pass. A fail, a timeout (`DRAFT_VERIFY_TIMEOUT_MS`, 2500) or an error keeps the draft unverified: never posted or cached, the operator reviews it.
- **Rule 7 in verify_answer:** a number from a cited "In-house test results" passage must be said with "in-house" or "our test" (`qualifier.is_qualified`). The LLM check let D007 ("increases by 38%" without the qualifier) through in 3 of 3 runs; code catches it every time.
- **Gate result** (tune half, 30 bad and 30 good drafts × 3 runs, measured from Korea): bad drafts posted **0**, good drafts blocked **0/90**, errors 0. Code alone: 29/30 bad drafts pass, 0/30 good blocked. LLM check latency p50 961 ms, **p95 1187 ms: above the 700 ms line**. A trivial flash-lite call from the same machine takes 680-760 ms (warm-up probes), so the line cannot be judged from Korea; it is measured on Cloud Run in us-central1 after the next deploy (agent-call latency of `draft_verifier` in the metrics). The sealed half stays with the planning session.
- **Tests:** `test_verify.py` (rule 7), `test_comment_pipeline.py` (a failed or erroring LLM check keeps the draft for the operator), `test_prompts.py` (prompt loads, examples match `DraftCheckOutput`).

D-127: The AI PD card and the question waiting list are one panel (option D; user, 10/5). Replaces the separate fixed card slot of D-113.
- No placeholder text: "AI PD: nothing to do right now" and the big "You have the floor." block are gone. When there is no card and no question, the panel shows one dim line ("No questions waiting.").
- A question card (answer, read out, which product) opens in place of its own row, so the question shows once; its "Posting answer…" bar sits inside the card's box. Any other card (promo, switch, wrap-up, shout-out), or a question card whose question is not on the list, goes on top. A question card that turns done as its row leaves keeps that row's place for its 1.5 s fade, so the list moves once.
- A shown card has a fixed height (200 px at 100%). The prompter box and the panel's outer box never move. Nothing in the panel animates (no FLIP, fade-in, fade-out or card expand); the list shifts once.
- **Check:** `e2e/demo.spec.ts` watches every animation frame of the demo; at each card change (on, off, swap of kind or text, status) it compares the prompter and the panel with the frame before. Run on the mock backend: on 3, off 2, swap 1, status 2, max change **0 px**. Unit tests: card in place of its row, non-question card on top, done card keeps its place, empty line.
- `node e2e/capture-scenes.mjs` still captures every scene; its one "MISSING" (S04 "SUGGESTED ANSWER") was already missing before this change (that text is no longer on any screen).

D-128: Per-agent thinking levels; Model Armor warm-up; measurements on Cloud Run (revision live-studio-us-00002, ab8446b).
- **Thinking per agent** (planning session's comparison, `docs/eval/models/README.md`; models fixed: flash-lite 3.5, flash 3.8): `COMPLIANCE_THINKING` LOW (0 of 183 false compliance alerts vs 3 at MINIMAL, same p95), `FACTS_THINKING` MINIMAL (LOW put 2 stray fact notes on non-fact lines), `CONTEXT_THINKING` MINIMAL, `TRIAGE_THINKING` LOW (intent 34.0 vs 32.7 of 35, same p95); the composer stays LOW. MEDIUM is out for the 3 s path (timeouts; adversarial detection fell to 43.7%). The levels override `LLM_FAST_THINKING` for those agents only (`utterance_judge`, `judge_single` and `draft_verifier` keep it); `/api/health` lists them under `agent_thinking`.
- **Model Armor warm-up:** on Cloud Run 1 of the first comments was left unscreened (the first call fetches a token and opens the connection, longer than 500 ms). The app now calls Armor once at startup, and the credential lookup runs off the event loop.
- **Draft verifier on Cloud Run** (9 calls from the demo bursts and feed): p50 642 ms, **p95 829 ms, still above the 700 ms line** (from Korea: p50 961, p95 1187). The check runs in the background after the composer (p50 1.8 s, p95 3.8 s in the same run), so it delays a composed answer by about 0.65 s and does not touch the alert path. Whether to accept that or trim the check is open (planning session and user).
- **Verifier prompt:** a yes/no question answered by stating the correct order, time or condition from SOURCE counts as answered (sealed D104, run 0). Tune half after the change: 0 bad drafts posted, 0/90 good blocked, 1 timeout (a bad draft, so blocked anyway).

D-129: JAPAC step 0a: Singapore's rules split into a market pack (law) and a language pack (wording). Plan approved by the user in the planning session (docs/research/japac-regulators.md).
- `data/markets/sg.json`: regulator (HSA), policy id, tier, currency (SGD, S$, 2 minor units), offered broadcast languages with their chirp_3 code (`en` → `en-US`, because chirp_3 rejects en-SG), sources, severity display, softening guidance, and the 15 rules with a stable `category` id, legal reference, title, description and severity.
- `data/lang/en.json`: per category the reflex phrases, unacceptable examples and say-instead hint; the negation and quote cues.
- `DataPack.load(data_dir, market, lang)` builds the same `ClaimRulesFile` as before. It fails fast when the market does not offer the language, when the language pack lacks a category's wording, or when the products are priced in another currency than the market's. Settings `MARKET` (SG) and `BROADCAST_LANGUAGE` (en); `STT_LANGUAGE` is empty by default and then comes from the pack.
- **Regression gate:** the rules built from the two packs equal the old `data/policy/claim_rules.json` field for field (checked before removing it), so the judges, reflex scan, prompts and every Singapore eval see the same input. Tests: 664 backend, 146 frontend.
- Next (0b): the English-only spots in code (verify `_TOKEN` and `_SENTENCE_END`, `number_set`, `corrections._IN_HOUSE`, `qualifier._QUALIFIED`, `publish.UNSURE`, spoken-number tables, prefilter `_PHONE` +65) move to the language and market packs, and each guard declares the languages it supports (an unsupported guard means no auto-post).

D-130: Context cache creation is single-flight in the background and shared across sessions (the adversarial run logged "context cache preparation failed for fact_checker" 202 times).
- **Cause:** the creation (count tokens, then `caches.create`) ran inside `asyncio.wait_for` with the caller's small budget (`min(1 s, deadline/5)`, 0.6 s for the fact checker). `caches.create` takes longer, and `wait_for` cancels what it waits for, so the creation was cancelled every time and never finished. The key also contained the session id, so every new session (every eval case) started again, and the log line had no reason.
- **Find it:** `grep "context cache" <log>`; the usage of a fact-checker reply shows `cached` near 0 for every call.
- **Fix:** one creation task per (agent, model, prompt version, system instruction, static prefix), started once and never cancelled by a caller: a caller waits up to its budget through `asyncio.shield`, then runs uncached, and the next calls use the cache. A failure logs its exception once and cools down for 60 s. Live check (Vertex, 5 sessions): from the second session on, the fact checker had 4,147 of about 4,778 prompt tokens cached; no creation failures.
- **Tests:** `test_context_cache.py` (slow creation is not cancelled and serves later calls; two sessions share one cache; the failure reason is logged).

D-131: A say-instead line with an in-house test number carries the qualifier (holdout H090, planning session's D-128 rerun).
- The host corrected with "it helps keep skin hydrated for up to 24 hours" and got a BRAND-TEST-QUALIFIER MEDIUM, which D-105 makes correct. But the line came from a say-instead built from the approved claim "Helps keep skin hydrated for up to 24 hours.*": when the judge copies such a claim without its '*', `spoken_claim` cannot add the qualifier, so we would tell the host a line that then raises an alert.
- Now every non-qualifier violation's say-instead goes through `qualified_say`: if it is not qualified and contains a number of one of the product's in-house results (on-air product first), it becomes that result's approved wording ("It helps keep skin hydrated for up to 24 hours in our in-house test."). Lines without such a number are kept. The rule hints in `data/lang/en.json` already carry the qualifier.
- **Tests:** `test_qualifier.py` (qualified say-instead from an unstarred copy; a line without a test number is kept).

D-132: A statement of the on-air product's sheet is never a compliance alert (sealed adversarial round 2, AW010).
- "Contains no added fragrance and no essential oils, making it suitable for all skin types." (cream) got ASEAN-2D-VULNERABLE HIGH once and BRAND-SUPERLATIVE MEDIUM twice; the cream's sheet says "Skin types: All skin types" and "It is suitable for all skin types and all users".
- D-123's approved-wording check now also reads the on-air product's sheet passages, one sentence at a time (words from different sentences never add up): Product overview, Key facts, Key ingredients, How to use, In-house test results, and FAQ answers (not the questions). Not Cautions, and not "Approved on-air claims", whose passages also list the claims NOT approved (a first version matched "the best moisturiser in Singapore" there; a test caught it). The 80% content-word and every-number conditions stay, and the test-qualifier rule is still exempt.
- A span with an extra word the sheet does not have stays an alert: "making it suitable for all skin types" covers 75% and still alerts (lowering the line would let "suitable for all skin types forever" through).
- **Tests:** `test_qualifier.py` (a sheet statement raises no alert; a wider claim still alerts; the sheet's not-approved list never counts as approved).

D-133: Every alert on the host screen acknowledges its render; voice driver `lines` mode (proof-plan §2).
- Only the HIGH overlay sent `POST /alerts/{id}/rendered`, so MEDIUM banners and fact notes had no render time. `FactNote` and `MediumBanner` now ack on mount too (a banner that carries the sentence's fact note acks both). Metrics' alert render times now include MEDIUM alerts.
- `node e2e/rehearsal-voice.mjs lines <file> [runs]`: each JSONL line (id, text, product, kind, rule_id or field) is spoken on its product (switched first when needed). The driver waits for an alert of the line's kind (if shown but not acked within 3 s, the alert is kept with no render time) and records STT, server and render times from the end of speech, plus per-final evidence (compliance verdicts, fact claims, alerts). The report (`docs/rehearsal-lines.json`) gives per kind the p50/p95/max of each stage, misses, wrong rule or field, and the share shown correctly within 3 s.

D-134: JAPAC step 0b: the English text guards read a Lexicon from the pack (A-shaped, B-ready; planning session's decision).
- `data/lang/en.json` gains a `lexicon`: stopwords, number words (ones, tens, decimal word, a lone "one" ignored), stemming suffixes, prefix length for STT slips, patterns (unsure/hedge, test qualifier, in-house, sentence end and split, clause split) and chat reactions. `data/markets/sg.json` gains the phone pattern (+65). The values were copied from the code by a script.
- `logic/lexicon.Lexicon` compiles them and holds the language helpers (`content_words`, `coverage`, `claim_words`, `spoken_numbers`, `split_sentences`, `is_qualified`, `is_unsure`). `DataPack.lexicon` builds it; `Catalog.lexicon` and `Reflex.lexicon` hand it on. The module globals are gone (`corrections.STOPWORDS/_ONES/_TENS/_IN_HOUSE/content_words/coverage`, `qualifier._QUALIFIED/is_qualified`, `publish.UNSURE/spoken_numbers`, `verify.split_sentences`, `reflex._SENTENCE_SPLIT`, `prefilter._PHONE/REACTIONS`). Per-session packs (step B) then only change which pack a session holds.
- **Regression gate:** before the globals were removed, the Lexicon gave the same result as the old functions on 2,112 texts (every eval text, product claim and passage): 0 differences. After: 672 + 2 tests pass; offline re-scores unchanged (adversarial tune PASS 99.2%, 0 wrong HIGH; verbal post public and hidden 0 false, 0 missed; draft gate 29/30 bad pass the code alone, 0/30 good blocked).
- Still English-only, for the per-market number parser step: `verify.number_set`, `_TOKEN`, `_UNITS` and `_LABELLED` (digits, "S$", "ml"), the profanity list, `reflex.normalise` (Unicode-aware but space-separated words), and `broadcast_summary`'s own sentence split.

D-136: Feature B1, a speakable correction line on the fact note (feature round of GPT, Gemini and Sonnet).
- The fact note's big line is now one sentence the host can read out: "{product}: say {value}", and " during the {promo}" when the right value comes from the active price promotion (no sheet passage), e.g. "Cream: say S$32.40 during the time sale". The product is the note's product short name ("the cream" → "Cream") or the set's label. The separate "Say this instead." label is gone from the fact note (the line says it). From the note's existing fields; no new detector.
- Not yet measured: the planning session's pass line (100% of fact-eval cases show the right product and value; read aloud through the spoken-number normalizer, the line clears its own note 100%).
- Tests: `host.test.tsx` (product on the line; promo condition; set label).

D-137: Feature B2, judge-health dot ("silence must not look like safety").
- The utterance pipeline counts, per judge (compliance, context, fact checker; or the single judge), the finals in a row on which it failed (timeout, error, invalid). At 2 (`HEALTH_STREAK`) it emits `judge.health` with the degraded judges; the judge's next answer clears it. The snapshot carries `judge_health`.
- The host's prompter header shows a neutral dot after the required-points count; it turns amber with "AI check slow" (tooltip: "alerts may be missing") while any judge is degraded. One failed final alone changes nothing.
- Tests: `test_alerts.py` (each judge: amber after 2 failed finals, back after 1 answer; 1 failure is nothing), `host.test.tsx`, reducer sample. Not yet run: the planning session's live pass lines (amber within 8 s when a judge is forced to time out, 3/3; recovery within 8 s; 0 amber across a healthy 12-minute show).

D-138: Feature B3, extend segment (+2 min).
- `POST /sessions/{sid}/segments/extend` adds 120 s to the on-air segment's `planned_duration_sec` and emits `segment.extended`. The operator has a "+2 min" button on the on-air run-of-show row; the host presses E.
- Everything that reads the plan moves with it: the host status line and the operator run of show (they now use the segment's plan, the run sheet's only before the segment starts), the overtime check (it can report once more after the new end; the client drops the old badge), and the AI PD's wrap-up and switch thresholds (`planned_ms` from the segment). Nothing on the host screen changes size.
- Tests: `test_alerts.py` (plan, overtime reset, PD planned time, event), reducer test, host key E. Not yet run: the planning session's pass line (no wrap-up card before the new 100%; status line exact; 0 px layout change) on a live show.

D-135: Comment-flow fixes from the planning session's first comment-flow eval (A1-A8).
- **Product attribution:** a comment that names no product is about the product on air (before the first segment: the first run-sheet product, which the host screen already shows as NOW), whatever basis triage gave ("ml?", "SPF?", "dry skin here, suitable?"). A product after an exclusion cue is not meant ("ampule price, not cream" → ampoule; cues in `en.json` `exclusion_cues`); "ampule" is an ampoule alias. A price question naming both products is `set_price`; a set price asked before air takes the first product in show order.
- **Triage prompt:** skin-type questions (also "heavy on oily skin?") are `skin_type_suitability`; both products together are `set_price`; a sheet-answerable product question is never `other` ("ml in this jar?" volume, "has perfume?" fragrance, "SPF?" ingredients, "use at night?" how_to_use); groups are matched by meaning, not wording.
- **Grouping:** for intents that hold one question per product and slots (price, set price, volume, fragrance, texture, shelf life, origin, packaging, skin type, pregnancy, age), the only open group that fits is joined even without a matching candidate id or wording.
- **No verified answer:** a host question, or any product question in a solo show, stays on the host's list (`needs_review`, `no_verified_answer`) and the AI PD card carries a fixed honest deferral (`notices.json` `host_deferrals`, general or sensitive; DRAFT wording for the user's review); in a team show the others go to the operator. A verified draft that arrives later restores the intent's route (it used to stay with the operator for good). A sensitive question with a verified draft now shows that draft on the host card. A verified AUTO draft marked `needs_human` goes to the host in a solo show.
- **Draft checks:** rule 6 stays inside one clause (split at . ; ( ) ", " and "and"), skips units and fillers when measuring distance, and accepts a number that any subject of its clause has; it no longer blocks "S$36.00 during this live (list price S$48.00). The set with the ampoule is S$62.00." The verifier treats a leading Yes/No as a statement. The composer answers only what is asked (a volume question got "50 mL airless pump tube" and the uncited packaging was blocked).
- **Results** (comment-flow eval, 12 scenarios, Vertex): baseline FAIL with route 85.7%, stale/wrong posts 7, host answers before confirm 1, cache 80.8%, recall 82.0%; after the first fixes route 97.9%, host early 0, cache 92.3%, recall 88.9%; after grouping recall 98.6%. The remaining "stale or wrong posts" are label phrases: the posts say "has not been specifically tested" where the key phrase is "not specifically tested", and a correct tingling answer lacks "patch test". "SPF?", eczema, retinol, vegan and a smaller size have no answer in the sheet and correctly go to the host with the deferral; their gold labels say AUTO.
- **Tests:** mapping (exclusion, set before air), grouping (single-question intents), comment pipeline (solo vs team routing, deferral card, route restored by a later verified draft), verify rule 6 regressions.

D-139: Show-replay support (proof-plan §1). `POST /demo/reset {assistant: false, show_mode?}` creates a session whose finals and comments are stored and shown, but no reflex chip, judge, triage, answer or AI PD runs (the baseline without the assistant). `POST /sessions/{sid}/demo/comments {author, text}` posts a scripted viewer comment while viewer input stays off. Test: assistant-off stores, never answers.

D-140: Step F, general questions in a solo show (planning session).
- Shipping, returns, payment, order status, giveaways and other no-product questions wait on the host's list in a solo show (`HOST`, `general`); nobody watches an operator list there. The AI PD offers a card with the general deferral line only once `HOST_REPEAT_THRESHOLD` (3) viewers ask. A triage failure keeps its `ai_unavailable` reason and waits in the list without a card. Team shows: the operator, as before. General groups are candidates for the host list whatever product is on air.
- Note (planning session): the deferral promises "I'll reply in the chat". The unresolved list must make that follow-up easy (post to chat from the list); not built yet.
- Tests: solo vs team; no card at 2 askers, the general deferral at 3.

D-141: Drivers share the service; show-replay harness; solo deferral lines.
- Two drivers (the planning session's lines run and my replay smoke test) kept deleting each other's sessions: both called `/demo/reset`, which drops the latest session. `POST /demo/sessions {assistant?, show_mode?}` now creates a driver session that deletes nothing; the drivers use it (falling back to `/demo/reset` on an older service) and end their session when done. `/demo/reset` keeps its studio meaning.
- `frontend/e2e/show-replay.mjs <file> [--assistant on|off]` (proof-plan §1, synthetic arm): replays a scripted show on the real path (host lines by TTS through the mic WebSocket at their `t_s`, scripted comments, promo starts and switches through the API) with the assistant on and off, polls the operator state every 2 s, and scores per show: (a) planted errors alerted within 3 s of the end of speech, by kind (a final belongs to the spoken line it overlaps most); (b) red and yellow alerts on safe lookalikes; (c) per question group the first handling (auto-answered, host card, honest deferral card, posted, never) and its time from the first ask, late over 60 s; (d) operator actions needed (planted errors not alerted plus groups never handled); (e) AI posts for unanswerable groups (wrong) and price answers written before a promo but posted after it (stale). Writes `show-replay.json` and `.md`, on and off side by side. The voice drivers share `e2e/voice.mjs`.
- Solo shows: the deferral lines promise no chat reply ("Good question! I don't want to guess, so I'll check that for you."; sensitive: "Everyone's skin is different, so please check with your doctor or dermatologist before using it."). Team shows keep the "I'll reply in the chat" lines; the operator replies from the list ("Write reply" on the question desk). Wording goes to the user (DRAFT).

D-142: JAPAC step B: each session holds its own (market, language) pack (planning session: per session, before step 1).
- `Session.market` and `Session.lang`, set at creation (`POST /sessions {market?, lang?}`, default `MARKET`/`BROADCAST_LANGUAGE`) and frozen for the show. A pair the market does not offer is refused (400 `unknown_market_language`).
- `AppContext.pack_for(market, lang)` loads a pack and its Reflex once and caches it; the settings' pair is `ctx.pack`/`ctx.reflex`. `SessionRuntime.pack` and `.reflex` come from the session; its catalog, judges, comment pipeline and AI PD use them (no `ctx.pack`/`ctx.reflex` inside a session any more).
- Speech-to-Text: the audio WebSocket opens the stream with the session pack's chirp_3 code; `STT_LANGUAGE`, when set, still overrides it.
- Setup shows the market and broadcast language of new sessions as a read-only chip (`GET /setup/market`), since only Singapore/English exists. The retriever and products are still shared (one market's products); per-market products and prices come with step 1.
- Tests: default pair; refused pair; two sessions with two languages on one service (own pack, reflex, lexicon, STT code; loaded once); setup chip.

D-143: Skin-type suitability is not a vulnerable-group claim (sealed adversarial round 2, AW010: "…making it suitable for all skin types" got ASEAN-2D-VULNERABLE HIGH in 2 of 3 runs; D-132's sheet match stays below 80% because of "making it").
- The rule's description (`data/markets/sg.json`) and the compliance job (same bullet in `utterance_judge.md` and `compliance_judge.md`) now say: saying which skin types the product suits is a cosmetic suitability statement; vulnerable groups are people with or at risk of a condition (pregnancy, breastfeeding, babies, children, eczema) and safety promises to them. No case sentence is quoted. To be confirmed on the sealed set by the planning session.

D-144: A slow fact call still shows its note; the health dot counts failures in a window (cloud lines run LT055: the fact checker timed out at 3001 ms twice, 58 s apart; no note, and the dot stayed neutral).
- The fact checker's deadline is `FACT_LATE_MS` (6000). `FACT_TIMEOUT_MS` (3000) stays the "on time" line: a fact call slower than it counts as a timeout for the health dot, but its contradicted note is still shown (a late correct note beats none). Late notes stay in the alert latency metrics as they are.
- Health dot: a judge turns it amber when it failed `HEALTH_STREAK` (2) times within `HEALTH_WINDOW_MS` (60 s), even with on-time answers between; its next on-time answer clears it. One failure alone, or two more than a minute apart, is nothing.
- No retry: a second call cannot fit in 3 s (planning session).
- Tests: two failures 50 s apart with an answer between turn amber, the next answer clears it, a lone failure 70 s later does not; a slow fact call counts as a timeout.

D-145: Speech-to-Text restarts overlap a warm standby stream (planning session; 3 of 300 cloud lines had a 3.3-3.9 s STT final, and the restart logs show a restart every 182-188 s of audio).
- From `PREWARM_MS` (165 s) into a stream, a second StreamingRecognize call opens and gets the same audio, without reporting. At the first final after `SOFT_RESTART_MS` (180 s), the standby takes over: its results that end by that final's end (+300 ms) are dropped (the old stream reported them) and the old stream is closed. The new stream has had 15 s of audio, so it is past its start-up when the host speaks again.
- Fallbacks stay as before: no standby ready (it failed or opened after the last final), the hard limit (240 s) without a recent final, or a stream error: close and re-send the audio after the last final into a new stream (with the old backoff on errors).
- Logs: "speech stream switch #n to the warm stream after X s of audio (standby had Y s)", "restart #n (limit|error)", and "first result Z ms after it took over; first speech audio W ms after" so a slow first final can be split into silence and start-up.
- Tests (fake recognizer): the takeover reports every word once, in order, with no word lost; without a standby the bridged restart still works.
- **Fix after a real-STT check (same day):** a local server with short constants (switch every ~25 s) showed that the replaced stream, cut off mid-sentence, still finalized its fragment ("This serum will fill them") while the new stream reported the whole sentence. The replaced stream now reports only results that end by the switch point. Re-run: 9 switches over 16 lines, every line complete, no fragment or repeat, STT finals 0.8-1.0 s; after a takeover the first final comes about 3 s after the host starts speaking (the line's own length). Per-final debug logs (`stt lane … emitted|standby|before switch|after switch`) stay at DEBUG. Test: a recognizer that finalizes a cut-off word reports no fragment after the switch (fails without the fix).

D-146: Fixes from the first sealed show replay (SEED1, assistant on, 00005: 7 of 22 question groups never reached the host; 1 red and 2 yellow false alerts of 12 lookalikes).
- **Host-card ceiling:** a beginner talks with 5-7 s gaps, so the 8 s pause never came. A waiting question with a card ready (verified draft or deferral) is due after `CEILING_MS` (90 s) on the host's list, `URGENT_CEILING_MS` (30 s) when sensitive or with 3+ askers. A due card shows at the next natural break (`BREAK_MS`, within 2 s after a final) or pause, at least `DUE_GAP_MS` (20 s) after the last question card; urgent ones first. A red alert still pre-empts every card.
- **A spoken answer before the draft:** the host answered about 3 s after the asks, before the 4-5 s draft. Such an answer (judged as an answer to a group still being drafted) is remembered; when the draft verifies (within 30 s), the context judge is asked once more with the draft, and the usual spoken-answer rules decide (D-110, D-112: consistent, verified, no alert, not stale). Consistent: the draft is posted as the host's answer; else nothing.
- **Qualifier across a split:** speech-to-text made "In our in-house test." its own final before "skin hydration went up 38% …". A short lead-in final just before (naming our test, no number, at most 8 words) now qualifies the next line. The later truly unqualified "38% …" got no alert because the false alert of the same result was still active (D-108 repeat rule); with the false alert gone it alerts again.
- **Cautions are not claims:** the compliance job now says that repeating a product caution or telling viewers to check with a doctor first is never a violation (the sheet's pregnancy caution got a red alert).
- Tests: PD ceiling (fresh vs due, break, urgent first, gap, red alert), early answer (consistent: posted; not: nothing), lead-in qualifier (passes only with the fix), prompts.

D-147: One product for every set question; more vouching phrasings (planning session's local regression on 24e37e3: sealed round 2 PASS, 97.5% detection, 0 wrong HIGH, 0% false alerts; comment flow 100% route but cache 96.2%).
- CF10 drafted the set price twice: "how much for cream and serum set?" took triage's explicit product (the cream) while the other set questions took the ampoule on air: two groups for one set. A set question (`set_price`, `routine_order`) now always uses the product on air, else the first named (or first) product in show order. The demo's mock composer fixture for the B1 set question is re-keyed to the cream (the product on air there).
- Vouched quotes (3 of 90 sealed runs): the compliance job lists more paraphrased ways of agreeing after a quote ("she's not overstating it one bit", "I'm with him on that", "I'd say the same", "every word of that review is right") and says the agreement may come in the next sentence. No case sentence.
- Tests: mapping (set questions use the product on air; before air the first in show order); bursts B1-B4 with the new fixture.

D-148: Fixes from the six sealed show replays on 00005 (ON vs OFF: operator actions 41 vs 93, planted errors 13/18 within 3 s; new bugs below).
- **Live price during a time sale:** "It's $36, very cheap" after the sale started got no note; the fact prompt let the live price count as supported. Now the live price said as the price now is `contradicted` (field `promo`, right value the sale price); only a clear contrast ("normally thirty-six, now …") keeps it supported. A code rule backs it: during a price promo, a supported live price of a promo product becomes the sale price unless the sentence has a contrast cue (`en.json` `price_contrast_cues`). A note on the live price (field price) is corrected by the sale price said later (field promo): both count as one price subject.
- **Promo terms:** the fact checker's ACTIVE_PROMO now carries `discount_pct_off_live_price` and `duration_min`; a different discount or duration is contradicted. Code accepts such a correction only when the right value is one of the promo's own terms and the host said another number (it used to accept promo prices only, so "extra 20% off" was dropped).
- **After a switch:** "this one", "it" and "also" refer to the product on air ("this one is also 50 ml" about the ampoule).
- **A topic word is not a claim:** STT made "Acne, um, no no," its own final and the judge flagged "acne" HIGH, 2 s before "we cannot say it treats acne" corrected it. A final that is nothing but the flagged word and fillers (`en.json` `fillers`) raises no alert; the judge prompt says the same.
- **Not product bugs:** the "stale" set-price post in SEED3 was posted 4 minutes before the time sale started; the replay harness counted every promo start (now only price promos, at the server's start time). The 8.3 s absent-ingredient note ("a little bit of alcohol") was model latency; the absence check itself is a code scan, and D-144 now shows such a note by 6 s at the latest.
- Live check (Vertex, 2 runs): S$36 during the sale, "an extra 20% off", "this one is also 50 ml" after the switch all caught; the "Acne, um" fragment raised nothing. Tests: post-validation (stale price, promo terms), topic word, promo input terms.

D-149: A gift offer's spend threshold is a structured, checkable fact (planning session's queue).
- `Promo.min_spend` (market currency); the gift pouch has 60.0. The fact checker gets the running offers that change no price as `ACTIVE_OFFERS` (title, `min_spend` display, duration); a different threshold ("free pouch over $50") is contradicted with field `promo`. Code accepts the correction only when the right value is a running offer's own `min_spend` and the host said another amount (no offer running: no note).
- Tests: offers input; a wrong threshold stands, a made-up one or one with no offer running does not.

D-150: JAPAC step 1, option (c): the Malaysia pack is in, Malaysia is not selectable until RM product data exists (planning session; the user owns the product data and will give the Malaysian prices).
- `data/markets/my.json` from the planning session's draft (`docs/research/packs/my.draft.json`): NPRA, MYR/RM, English broadcast (`en-US`, chirp_3 has no en-MY), phone numbers with +60 or a leading 0, the 23 rules (ASEAN base, brand rules and 9 Malaysia-only rules). The draft's descriptions of the Malaysia-only rules were reviewer notes; they are replaced by rule text the judge can apply (absolute safety, uncertified halal, government approval, competitor comparison, professional endorsement, unsupported evidence and before/after, testimonials, GMP promotion, religious claims). Sources may be online-only (`PolicySource.file` optional).
- `data/lang/en.json` gains English wording for the 8 new categories: paraphrased examples, conservative reflex phrases (none for testimonials and religious claims), say-instead hints that point back to approved wording.
- Tier: market and language `preview`. A preview session posts nothing by itself: AUTO questions go to the host (`HOST`, `preview`), spoken answers are never auto-posted (also the early-answer recheck), and the host top bar and operator header show "PREVIEW · <market>". The snapshot carries `market` (code, name, language, tier). Live once a Malaysian sealed set passes.
- The judge, triage, composer and AI PD prompts no longer say "in Singapore"; the RULES carry the market (triage mentions Singlish and Manglish).
- `DataPack.load(…, "MY", "en")` still refuses: products are priced in S$ (D-129 kept). Next, when the user gives RM prices: Malaysian products, sheets and promos per market.
- Tests: the Malaysia rules build (23), the load is refused for the currency; a preview session sends an AUTO price question to the host and posts nothing; host preview label.
- **Rule texts checked (GPT against NPRA Annex I Part 8 / Part 10 and the 2011 halal order):** 2 of the 9 Malaysia-only texts were right (government approval, competitor comparison); the other 7 are replaced by the checked texts (absolute safety incl. "safe because natural", GMP incl. ISO 22716, religious statements, professional endorsement with its exceptions, unsupported evidence and before/after without elapsed time, testimonials, halal certification and marking). Wording: reflex "no harmful effects" (absolute safety; this category's wording is shared with Singapore, where it only adds a provisional chip for the judge), "iso 22716" (GMP); removed "unlike other brands", "clinically proven", "scientifically proven" and "halal certified" from the reflex (they also catch allowed statements; the judge decides); the professional and before/after examples now show the violation itself.

D-151: Fixes from sealed adversarial round 3 (planning session, 9a39849, 80 lines × 3: PASS, detection 99.2%, 0 wrong HIGH, 0 wrong texts, false alerts 4.2% of 5%: two classes).
- **A late qualifier:** "Redness went down 30% after two weeks." then, as its own final, "That's from our in-house test." The judge saw the fix but listed no correction (3/3 runs), and once the add-on was judged before the number, so no alert existed yet. Now a short final that only names our test (qualified, no number, at most 10 words) corrects an active or provisional qualifier alert of the same segment from the last 10 s; and when such an add-on followed a final within 10 s, that final's qualifier violation raises no alert (the race). An add-on with its own number is a new claim and fixes nothing.
- **A correct absence contradicted:** "No retinol in this one" came back contradicted with "not in this product" (2/3 runs). A stated absence (`en.json` `absence_cues`, "-free") is never contradicted by an absence; an ingredient the sheet does list still contradicts it through a quoted passage. And any contradiction whose right value restates the stated value (same numbers, or the same text) is dropped.
- Vouching: "and the same happened to me" joins the paraphrased agreements after a quote (1/3 runs missed).
- Tests: late add-on corrects; add-on judged first prevents the alert (fails without the fix); an add-on with its own number does not; absent vs absent dropped, present vs absent kept; a restating correction dropped.

D-152: Fixes from the comment-flow runs on revision 00007 (planning session).
- **CF09, a draft check timeout:** a correct sale-price draft went to the host as `no_verified_answer` because the LLM draft verifier timed out. A timeout is not a block: the check now runs once more on timeout. And when a new asker joins a group whose draft failed only to be checked (`draft_check_timeout`, `draft_check_error`, `draft_check_invalid`), the group drafts again.
- **CF10, two drafts for one set-price question:** in the first seconds of a session the grace lookup (`segment_at(received - grace)`) found no segment, so the context fell back to the first run-sheet product (cream) while the ampoule was on air. The lookup now falls back to the segment on air before the run sheet. Also, a single-answer intent (price, set price, volume ...) keys its answer by product, slots, promo state and documents only, not by the question's wording, so two groups of it share one draft.
- **CF11, a document change (pairwise precision 70%):** after a /setup upload, askers joined the open group answered from the old documents. A document change now closes open, answered groups whose answer key no longer matches (`closed_reason` "documents_changed"), as a price promo change does, so the next asker gets a fresh answer.
- Tests: timeout retried once; a new asker re-drafts an unchecked draft; an early comment takes the product on air; single-answer groups share one key, other intents do not; a document change closes the stale answered group (all 5 fail without the fix).

D-153: Fixes from the first 00007 show-replay reasons (planning session, SEED1/SEED2 with the assistant on: no question reached a host card in either 12-minute show).
- **Due host cards never shown:** a talkative host never pauses 8 s, so a waiting question is only offered once it is due (D-146 ceiling). In the cloud the AI PD model chose "none" ("host is mid-topic") for it, and the decision cache (`_last_cands`, the candidate ids) then skipped every later decision with the same ids, so the due card was never decided again. Now a pulled, pushed or due question is `forced`: when the model says "none" to a set that holds one, the rules show it. The cache key also holds each candidate's priority, so a question that becomes due is decided again. The local runtime uses the rules only, which is why the 60 s smoke test showed a card.
- **Routing:** how-to-use, routine-order, skin-type, makeup, results and comparison questions route HOST by `intents.json` (advice in the host's voice); that is by design, not a solo-show fallback.
- **Empty drafts for "How many drops?":** BM25 with the product name in the query never ranked the ampoule's "How to use" steps (also not in the top 6), so the composer answered nothing. `how_to_use` and `routine_order` now always add the "How to use" section (as D-068 does for origin, texture, cautions ...). The real composer then answers "Apply two to three drops ...". "Is the ampoule a serum?" was answered correctly by the real composer for every intent tried; the replay's exact question is needed to trace that case.
- **Answered on air:** the show replay scores a group the host answered aloud (`host_verbal_answer_transcript_id`, not posted) as `answered_on_air`, not `never`. The runtime logs each spoken-answer decision with its reason (`host answer <sid> <group>: <action> (<reason>)`), so a verified draft answered aloud but not posted can be traced to the judge (inconsistent), the number check, staleness or an alert.
- Tests: a due card shows when the model always says "none" (fails without the fix); how-to-use and routine-order questions get the "How to use" steps (fails without the fix).

D-155: A qualifier merged with its fragment (00007 show replays, class G and the two yellow lookalikes).
- **Cause:** "Hydration went up 38% right after one application," then "in our in-house test." The fragment ends with a comma, so the add-on is judged merged with it (D-088). D-151 looked for an add-on in the merged text, which holds the number, so the add-on was never recognised; and a merged judgment never resolves its fragments' alerts. The fragment's false alert stayed active, and a minute later the real unqualified repeat ("The cream gives you 38% more hydration right after you put it on.") was taken for the same alert (D-108) and got none. Reproduced with the real judges 3/3; not a judge miss: alone, or after a qualified line, the repeat alerts every time.
- **Fix:** the add-on is recognised on the final's own text, merged or not, and corrects the qualifier alert of the fragment it completes (also before that alert exists, D-151's race rule). Real judges after the fix: the split line's alert is corrected and the repeat alerts (3/3).
- **E and F (a stale price after "So the cream," / "this one" after "same as the cream,"):** not reproduced. With my own sentences, split, period-ended, one line, digits and spelled-out numbers, the real fact checker gave the right note every time, on HEAD and on 9a39849 (00007). No code change; `scripts/probe_finals.py` runs any finals through the runtime with the real models and prints each final's fact claims and alerts, so the sealed finals can be traced locally without sharing them.
- Tests: merged add-on corrects the fragment's alert; merged add-on judged first prevents it; the same number later without the qualifier alerts (all 3 fail without the fix).

D-156: An ingredient the sheet lists as "Free from" (00007 show replay SEED3, class H).
- **Cause:** "I think it has a little alcohol inside" about the cream got no note. The fact checker answered "not in this product" without a passage, and the D-121 absence check then looked for "alcohol" anywhere in the sheet; it is there, but only in "Free from: ... ethanol (denatured alcohol) ...", so the contradiction was dropped. When the model cited the free-from passage the note came, so it was hit or miss.
- **Fix:** a word the sheet names only in its "Free from:" list counts as absent. Real models after the fix: the hedged line, the plain line and "a bit of ethanol" are all contradicted (3/3 for the hedged line alone).
- **I and J (yellow on the sheet's list price; yellow on approved claim wording):** not reproduced with my own sentences (2 runs each: both prices supported, both claims supported, no alert). The show replay now stores the rule, severity and fact field of each lookalike alert (ad8b4e2).
- Tests: "a little alcohol" and "ethanol" contradicted, "panthenol" (a real ingredient) not (the first two fail without the fix).

D-158: One log line per fact claim and per alert (planning session: Firestore keeps no session data, so Cloud Run logs are the only trace of a cloud replay). `facts <sid> t=<transcript>: <product> <field> said=<value> verdict=<verdict> correct=<value>` for every fact-check claim, and `alert <sid> <event> <alert_id> <kind> <rule> <severity> <status> t=<transcript> field=<field>` for every alert event (created, updated, escalated). A re-shown fact note is an `alert.updated` with the new transcript.

D-159: STT latency per final (00007 lines pass: two slow price lines got their final ~3 s after the end of speech, near a stream switch). Every final logs `stt final <ms> ms after speech end, stream #<n>` (n = the switch or restart that started the stream, 0 for the first), and the switch line gives how many results the standby returned before it took over. The standby already receives the live audio for ~20 s before the switch (D-145 prewarm at 165 s), so "dual-feed" exists; these lines show whether the first final after a switch is really slower, and whether a standby took over before it had returned anything, before any change to the switch.

D-157: A short comment is triaged with the host's last line; a failed draft is retried once (00007 show replays, class C; comment flow CF01).
- **RECENT_HOST_LINE:** "Over 60 how", "Pouch for set?" and "Tingling?" came right after the host talked about that topic, and triage, which saw only the comment and the product on air, read them as age, packaging or a reaction. A comment of at most 5 words now gets the host's last final (as judged, fragments joined) from the same segment within 30 s before it (`RECENT_HOST_LINE`, null otherwise), in the single and the batch triage. The prompt says a short fragment is often a reply to that line, with two examples of my own; the line is transcribed speech, data only. The triage cache key includes the line for such comments. Real triage with my own fragments: "Over 60 how?" after "Spend over S$60 today and the travel pouch is free." went from `shipping` to `promo`; tingle and warmth fragments stay `allergy_sensitivity` with the host's topic in the canonical question; controls unchanged.
- **Composer retry:** in CF01 every price asker had joined while the group's only draft timed out, so the group went to the host without an answer and nobody came later to draft again (a later asker already drafts again). A composer timeout or error is now retried once, as D-152 does for the draft check.
- **Evals (real models, without the composer retry):** comments ×3 (`docs/eval/2026-10-05-comments-3runs.md`): targets met in runs 1 and 2; run 3 missed by two timeouts while the comment-flow eval ran in parallel; C09 (label still OPERATOR, sensitive questions route HOST since D-113) and C33 (shelf_life vs other) fail in every run, as before. Comment flow ×2 (`docs/eval/comment-flow-d157.md`): kind, route 100%, must_not_merge 0, stale or wrong 0; cache 98.1% (CF04 run 0: the morning question split into two groups, recall 83%); host early 1 was the eval stamping the host's confirmation 16 ms after approve() had posted (fixed in 07c7163); CF11 recall 57% in both runs, because D-152 now closes the answered group at the document change and later askers form a new group, which the gold labels count as one cluster.
- Tests: a short comment gets the host's line, a long one or a line older than 30 s does not (fails without the change); cache key and batch items carry the line; a composer timeout is retried; two timeouts and then a new asker get the answer posted; the D-135 test now fails the composer twice.

D-160: The standby takes over only after it has returned a result (planning session's local SEED1 replay on c1cf35c: "switch #1 to the warm stream ... (standby had 20 s)", then "first result 4500 ms after it took over; first speech audio 0 ms after"; the unqualified repeat said at that moment alerted ~5 s late). The switch at a final past the soft limit now waits while the standby has returned nothing (logged once: "speech stream switch waits: the standby has returned no result after N s"); the live stream goes on and the standby takes over at the first chunk after its first result, from the same switch point. At the hard limit the old bridged restart still applies. The D-159 lines (results per standby, ms per final with its stream) show whether that is enough or whether the standby returns nothing while it stands by.
- Test: a standby opened 200 ms before the soft limit does not take over with 0 results, no bridged restart, no word lost or repeated (fails without the change).

D-161: A red alert blocks AI PD cards for 20 s, then waits as a header chip (planning session's local SEED1 replay on c1cf35c: a red nobody corrected blocked every card from 10:36 to the end, so host_card was 0; decided by the planning session after GPT, Gemini and Sonnet, provisional until the user reviews it; GPT's host "resume" tap was rejected as an extra host action).
- A compliance HIGH blocks AI PD cards for `RED_BLOCK_MS` (20 s, `logic/pd.py`, same value in `frontend/src/app/selectors.ts`) after it was created or escalated. A new distinct HIGH, or the same claim said again (a new alert), restarts it; an update of the same alert (provisional to active, a duplicate detection of the same transcript) does not.
- On the host screen the red takes the prompter only while fresh; after that it shrinks to a chip in the header ("⚠ N uncorrected", "미정정 N건"), and the card returns. Correction or dismissal clears the chip as before. Everything else a HIGH does is unchanged: no spoken answer is auto-posted while one is active, and a pending product switch is reset.
- The show-replay driver still never dismisses compliance alerts, so replays show the real solo case.
- To revert: set `RED_BLOCK_MS` very large in both places.
- Tests: an uncorrected red blocks the card while fresh, the card shows after the block while the red stays active (fails without the change); red_blocks by created and escalated time, MEDIUM and corrected never; host screen: a red past 20 s shows the chip and the card, an escalation brings the full red back.

D-162: Every final logs its text, cut to 100 characters, with the transcript it was merged with (`final <sid> <transcript>: '<text>' (merged with <transcript>)`), so one replay gives the exact STT split behind a false alert and the split can be probed (planning session: the pregnancy-caution red did not reproduce with any of 9 guessed splits).

D-163: A due question card is decided by the rules at once, without the AI PD model (planning session's local SEED1 replay on 3d324d3: "how to use" for the ampoule waited 285 s with a verified draft, its product on air the whole time).
- **Cause:** a due card is offered only at a break (within `BREAK_MS`, 2 s, after a final) or at a pause. The decision sent it to the model; the model call ran out (11 of 16 AI PD calls in that show were cancelled after ~2.1 s); the re-check after the call found the break over and dropped the card, and the unchanged candidate key (`_last_cands`) never decided it again. The AI PD call at 11:10:04.9, about 90 s after the question reached the list, is that moment.
- **Fix:** a pulled, pushed or due question has no choice left for the model (D-153 already overrode its "none"), so when the candidates hold one, the rules pick at once and the re-check runs in the same instant. The model still chooses among the other cards.
- **Logs:** every change of the host's list logs `hostqueue <sid> on_air=<product> list=[group:intent:score, ...] outside=[...]`, the candidates that did not fit in `HOST_TOP_N`, so "not on the host list" can be told apart (a full list, or another product on air, D-140).
- Tests: a due question with a model that times out after 2.5 s gets its card (fails without the fix); the D-153 test now asserts the model is not asked for a due question.

D-164: Product-type and sale-duration questions get a draft (planning session's local SEED2 replay on 3d324d3).
- **"Is an ampoule the same as a serum?":** triage read it as `product_comparison` (the show's two products), so the draft had no product, and the composer would not make a general claim about ampoules and serums ("The sources do not state whether an ampoule is the same as a serum"), 6/6 with the real models. The triage prompt now says that what kind of product it is ("is it a serum?", "essence or serum?", "is this a moisturiser?", my own examples) is `texture` about that product, with a canonical question about it, and `product_comparison` is only for comparing the show's products. Real models after: "Yes, it is an ampoule serum." 6/6, from the sheet's "Product type: Ampoule serum".
- **"How long will the sale last?":** triage gave `promo` with my wording, but the promo passage the composer cites held only the prices. It now ends with the duration from promos.json ("Runs for 10 minutes."), so the answer is "The time sale runs for 10 minutes." (4/4). A "N minutes left" answer would go stale in the answer cache and in replies posted again, so it is not offered; the triage prompt also says that how long a running sale or offer lasts, or when it ends, is `promo`.
- Comments eval ×2 (`docs/eval/2026-10-05-comments-2runs.md`): targets met in both runs; only C09 and C33 differ from the labels, as before.

D-165: An ingredient the product contains is never contradicted by another one (planning session's local SEED1 replay on 39c07fa: "The main ingredient is Niacinamide." got a note "Centella Asiatica Leaf Water").
- The ampoule's formula is built on centella water (50%, "formula base") and its headline active is 4% niacinamide; which one is the "main" ingredient is not a fact the sheet settles. With my own line "The main ingredient is niacinamide." the real fact checker contradicted it in 1 of 3 runs, then 3 of 4.
- Now an `ingredient` contradiction whose stated ingredient is on the product's sheet (not only in its "Free from" list) is dropped, unless the host stated an absence ("there is no niacinamide in it" still gets its note). After: no note in 4/4.
- The merge case from the same replay ("about 50% no plain water" + "Niacinamide" read as "50% Niacinamide") did not reproduce with my own split (3/3 read correctly); D-162's `final` lines give the exact split to probe.
- Tests: present ingredient dropped (fails without the change), absent ingredient and a stated absence kept.

D-166: The AI PD's ADK model keeps one genai client; the AI PD runs on gemini-3.8-flash at LOW with a 4 s deadline (planning session's decision after GPT, Gemini and Sonnet; ADK stays, the user chose an ADK AI PD).
- **Cause of the ~1.7 s:** the `LlmAgent` got the model as a name, so ADK built a new `Gemini` model object, and with it a new genai client (a new connection and credentials), on every call: per call one `Client.__init__` and a `generate_content` of ~2.1 s, against ~0.9 s direct. ADK itself, and the session create and delete, cost almost nothing. Now one `Gemini` object per model name is shared process-wide (`_gemini()` in `agents/ai_pd.py`), so only the first call of the process is cold.
- **After (docs/eval/ai-pd-arms-d166.md, 12 cases × 3):** flash-lite MINIMAL through ADK 994 ms p50 against 959 ms direct; gemini-3.8-flash LOW through ADK p50 2.1 s, p95 3.7 s, 2 of 36 over 4 s, gold 36/36 (before: p50 3.9 s through ADK).
- **Model:** the AI PD now uses `LLM_QUALITY_MODEL` at the new `PD_THINKING` (LOW); flash-lite chose no better than the rules (72% against 75%, docs/eval/ai-pd-arms.md). `PD_DEADLINE_MS` is 4000; a timeout still falls back to the rules, and due or pulled questions never wait for the model (D-163). The planning session rescores on its own sealed PD cases before this is final (`eval_ai_pd.py --cases`).

D-167: The fact checker sees where a merged utterance was split (planning session's local SEED1 replay on 39c07fa).
- **Cause:** "about 50% no plain water" (no end punctuation) and, 1.7 s later, "Niacinamide" were judged merged (D-088, within the window), and the fact checker read "50% Niacinamide" (contradicted, 4%). That re-showed the planted niacinamide note on the "Niacinamide" final, so it appeared on a line where the host was saying nothing wrong. The next line, 6.6 s later, was not merged (the D-162 `final` lines show no merge; the probe merged it only because `probe_finals.py` defaults every gap to 1500 ms: give each final its real `gap_ms`).
- **Fix:** the fact checker's UTTERANCE shows the merged finals with " / " between them (`FactInput.parts`; the plain merged text is unchanged for every code check and mock key), and its prompt says a fact takes a number from one part and its subject from the next only when the next part continues the same clause ("it is made with ten percent / niacinamide."), never when it starts a new sentence or topic (own examples).
- Real models: the logged finals with their real gaps: no contradiction 3/3 (before: 3/3 contradicted, planning session's probe); "And it is made with ten percent" + "niacinamide, which is a lot.": contradicted 3/3, as it should be.
- Test: a merged utterance reaches the fact checker as "A / B", a single final unchanged.

D-168: A question about a running offer is answered from the offer (planning session's local SEED2 replay on 39c07fa: the gift threshold and "pouch with the set" went to the host as general questions with no draft).
- The triage prompt says a question about a running offer's terms (how much to spend for the gift, whether a bundle also gets it) is `promo`, like a sale's duration (D-164).
- A `promo` draft gets each running offer that changes no price as a citable passage in its own viewer wording with its duration (`PROMO#promo_gift_pouch`: "Free DAON LAB travel pouch with orders over S$60. Runs for 15 minutes."), and the answer key of a `promo` question includes the running offers, so the answer changes when an offer starts or ends; price answers are not affected by a gift.
- Real models with the gift running (my own wording): "how much must I spend for the free pouch?" → "You need to spend over S$60 to get the free DAON LAB travel pouch." (2/2); "if I buy the set do I also get the pouch?" → the set and the S$60 threshold from the sources (2/2). Without a running offer there is nothing to cite, and the question gets the honest deferral.
- Tests: the offer passage text, a promo question gets the offer and a price question does not, the promo answer key follows the running offers and the price key does not.

D-169: A routine-order question names both products (planning session's local SEED2 replay on 39c07fa: "Should it be used before the cream?" came out empty).
- The question was attributed to the cream (D-147: a set question takes the product on air), and the composer read "it" as the other product: "wrong product", an empty draft. The cream's own sheet answers it ("If you use Deep Hydration Ampoule, apply the ampoule first"), and with a canonical question naming both products the real composer answered from it 3/3.
- The triage prompt now says the order in which to apply the show's products is `routine_order`, its canonical question names both products with "it" resolved, and which one to buy (first) is `product_comparison` (the first wording pulled the eval's C26 "which one should I buy first" into `routine_order` in both runs; the narrowed wording passes). Real models: "Should it be used before the cream?" with either product on air and "cream first or ampoule first?" answered 6/6.
- "How long does it take to see results?" stays without a draft: the sheets give no timeframe; only in-house test results carry times, which are test results, not a promise.
- Comments eval ×2: targets met in both runs, only C09 and C33 differ, as before.

D-170: The AI PD prompt defines "time nearly up" and puts a waiting question before "Next up" (planning session's 24 sealed PD situations on D-166: gemini-3.8-flash LOW 62/72; misses: "Next up" or a plain wrap-up chosen over a waiting question near the end, "Next up" chosen at ~70% elapsed, and the question off the host's topic chosen at a pause).
- "Time is nearly up" is now one minute or less left (`planned_s - elapsed_s <= 60`), from the fields SHOW_STATE already has.
- Priority 2 is only a switch or wrap-up card naming missing required points; a card with no missing point ("Next up", "Wrap up", "Required points done") is priority 4: only when no question waits and time is nearly up, else "none"; a waiting question always comes first.
- Same priority: the card on what the host is talking about in RECENT_LINES (two questions at a pause: the one on the host's topic), else the first.
- Two new few-shot examples of my own (Demo Balm): a waiting question before "Next up" at 35 s left; of two questions at a pause, the one on the host's topic. The sealed cases were not used.
- My 12 cases, gemini-3.8-flash LOW through ADK ×3 (`docs/eval/ai-pd-prompt-d170.md`): 34/36, p50 2.1 s, p95 2.9 s, none over 4 s; the two misses are the shout-out case, as in the first arms run.

D-171: A canonical question never widens what the viewer asked; usage duration is not shelf life (planning session's local SEED3 replay on 39c07fa: "free gift?" with no gift running got the AI reply "…live broadcast price of S$36.00 … live set price of S$62.00").
- **Cause:** triage rewrote "free gift?" as "Is there a free gift or promotion?". The price reply answers "promotion", so the composer and the LLM draft verifier, which see only the canonical question, passed a grounded reply that did not answer the viewer. The verifier itself catches a reply that does not answer its question: four pairs of my own (a gift question answered with the price, a sample question with the volume, cruelty-free with the fragrance facts, delivery with how to apply) were blocked 12/12 and two matching good pairs passed (`data/eval/draft_verifier_cases.jsonl` D120-D125; `docs/eval/draft-verifier-llm-d171.md`: bad posted 0, good blocked 0/96; the p95 latency line, 1270 ms against 700 ms, fails as it did before).
- **Fix:** the triage prompt says a canonical question never widens what was asked (own example: "free sample?" is not "free sample or discount?"). Real models: "free gift?" and "free gift with purchase?" stay as asked (6/6); "any freebie?" once became "free gift or sample". With no offer running the draft is empty ("The source passages do not mention any free gift."), so the viewer gets the honest deferral; with one running, D-168 answers from it.
- **C33** (relabelled by the planning session: "how many weeks does one bottle last if I use it every day?"): triage said `shelf_life` in both runs, so it would have been answered with the shelf life. The prompt now says `shelf_life` is only how long the product keeps, and how long a bottle lasts in daily use is `other` (no sheet states it). Comments ×2: 35/35 in both runs.

D-172: A line with no product continues the product just named (planning session's local SEED3 replay on 39c07fa: "…ampoule … $32," then, past the merge window, "list price 42": a note "S$48.00" for the cream on air).
- **Causes:** the fact checker's scope rule checks CURRENT_PRODUCT unless the line names another product, and its passages held only the products named in the line itself plus the one on air, so the ampoule's sheet was not even citable. Reproduced 3/3 with my own lines.
- **Fix:** the fact passages also take the products named in the last final, and the fact checker prompt says a line that names no product and has no "this one", "it" or "this" (a bare continuation, own examples "regular price 60", "and in 100 ml") is about the product of the last line of RECENT_TRANSCRIPT; deixis keeps the D-148 rule (the product on air after a switch).
- Real models: "list price 42" now supported as the ampoule's list price (2/2), "list price 45" contradicted against the ampoule's S$42.00 (2/2), no note for the cream (3/3); class F ("It's the same as the cream." then "This one is also 50 ml") still contradicted for the ampoule 3/3.
- Test: a bare continuation's fact passages hold the product the last line named (fails without the fix).

D-173: Answer linking: the on-screen mark is only a tie-breaker, and a read-out followed by its answer is an answer (planning session's verbal regression on a9fa6f5: V42 "There's no added fragrance in it, so it's gentle." answering the waiting fragrance question while the makeup card shows, missed 1/3 as "not an answer to an offered question").
- The context judge prompt now says the `on_screen` mark only breaks a tie: a sentence that answers a different open question answers that one (own example). A first rerun then missed V04 ("Raj asks about oily skin. Yes, it's a light gel-cream …") once, read as a read-out; the prompt now also says a line that reads the question out and then answers it is an answer (own example).
- Verbal eval ×3 (`docs/eval/verbal-post-d173.md`, `verbal-post-holdout-d173.md`): public 0 false, 0 missed; holdout 0 false, 0 missed.

D-174: Spoken numbers and durations, and a short flagged span inside sheet wording (planning session's sealed verbal set: 40 cases, 4 of 63 expected posts missed, two classes).
- **"twenty-one percent … a day later" against the draft's "21% … 24 hours":** the number check read "twenty-one" as 20, because "one" is a skip word (D-116: a lone "one" is no number) and was dropped before the compound was joined. A skip word is now dropped only when it stands alone. Durations: `Lexicon.durations()` reads "24 hours", "a day", "two weeks" as hours from the language pack's new `duration_hours` (en.json: hour 1, day 24, week 168), and a spoken number that is a duration equal to one in the draft is not "a number that differs" ("after seven days" for "one week later"). Percent and count values stay strict; a month is not converted.
- **"Guys can use it too, no problem, all skin types and all users." against the draft "Yes. It is suitable for all skin types and all users.":** reproduced with my own lines as verbal cases, 3 of 10 runs held: the compliance judge flagged the span "all users" (ASEAN-2D-VULNERABLE, HIGH). The D-123/D-132 approved-wording guard skips spans under 3 content words; a short span is now compared with the phrase around it in the utterance (between commas or sentence marks), here "all skin types and all users", the cream's own FAQ answer. A short span inside wording that is not on the sheet still alerts ("it even cures acne for all users").
- New public verbal cases V49-V51 (own lines: the two above, and "twenty-six of thirty … after twenty-eight days" against the sheet's "26 of 30 … after 4 weeks").
- Verbal ×3 (`docs/eval/verbal-post-d174.md`, `verbal-post-holdout-d174.md`): public 0 false, 0 missed; holdout 0 false, 1 missed (HV08, "not an answer to an offered question", 1 of 3). The answer-linking misses (V42 class) remain about 1 in 150 posts at either context thinking level (MINIMAL and LOW each missed once over both sets ×3), so `CONTEXT_THINKING` stays MINIMAL.
- Tests: compound numbers and equal durations pass, a different percent or duration is held; a short span inside sheet wording raises no alert, inside other wording it does.

D-175: A spoken answer the context judge did not link is asked about once more (user's rule, proof-plan §4: 100% in every run, no wrong, missed or double posts; design by the planning session).
- **Trigger:** the judgment links nothing (also when the context judge ran out: the compliance judgment then publishes with an unlinked answer instead of nothing), and `publish.relink_candidate()` finds exactly one offered verified draft the line seems to answer: every number the line says is in it (`verbal_check`, which also rejects a hedged line) and the line says at least half of its claim words. The pre-check never posts.
- **Second call:** the context judge again with only that question (on screen), off the 3 s path (`UtterancePipeline._relink`, like D-146's early answer). It posts only when `publish.decide` then says "post" with every usual check: the judge's link and consistency, the number check, compliance and facts of the line, and staleness; never in a preview market.
- **Evidence:** in the verbal eval run before the change, every one of the 8 remaining misses was a context-judge timeout (~2.5 s, Vertex slow at the time), not a wrong link. With the second call (`eval_agents.run` makes it as the runtime does; `eval_verbal_post` scores it): public ×3 0 false, 0 missed (5 timeouts, 4 second calls, all linked), holdout ×3 0 false, 0 missed (4 timeouts, 6 second calls; HV37 asked again 3 times and correctly not posted). `docs/eval/verbal-post-d175.md`, `verbal-post-holdout-d175.md`.
- Tests: the pre-check picks the one draft, and none for a different number, a hedge, an unrelated line or two equal drafts; a line linked to nothing is asked about once more and posted (fails without the change); a line with another number is not asked again; a context-judge timeout is asked about again and posted (fails without the change).

D-176: A failed triage is retried once; one draft per ingredient amount (planning session's comment flow ×2 on 5a77fdb: route 99.3%, cache 98.1%).
- **CF11:** one triage timeout per run (Vertex slow) turned the price question after the document change into `other` / `ai_unavailable`, with no answer. A triage timeout or error is now retried once, as D-152 does for the draft check and D-157 for the composer; a second failure keeps `ai_unavailable`.
- **CF12:** "What is the percentage of panthenol in it?" and "… in the ampoule?" formed two groups (ampoule, `ingredient_amount`) and drafted twice, because a non-single intent keys its answer by the question's wording. An `ingredient_amount` answer is now keyed by the product's key ingredients the question names (from its sheet, "Name: amount"; matched by the first five letters of each name's longest word, so "hyaluronic acid" is "Sodium Hyaluronate"); a question naming none keeps its wording.
- Tests: the same ingredient in two wordings shares a key, another ingredient does not, "hyaluronic acid" names sodium hyaluronate; a first triage timeout is retried and the price question is answered (both fail without the change).

D-177: An uncorrected red alert stays full size on the prompter until it is corrected or dismissed (user decision 10/5, relayed by the planning session; replaces the header chip of D-161).
- Cards stay blocked for `RED_BLOCK_MS` (20 s) after the red was created. After that, the AI PD card and the questions show below the still-full red; the "Finish the correction first" hint gives way to the Q hint.
- During its first 20 s the red is highlighted (a pulsing ring, `data-fresh`). The same wrong line said again in another final is a new alert (§8.4.2), so it highlights again and restarts the 20 s; so does a new red.
- The escalation (5 s after shown) no longer restarts the block, so the block is 20 s as decided, not 25 s. Server (`logic/pd.py` `red_blocks`) and client (`selectors.ts` `redBlocking`) count from `created_at` only.
- The "N uncorrected" header chip is removed.
- Tests: the PD card shows 20 s after an uncorrected, escalated red (fails with the escalation restart); an escalation inside the block does not extend it; host screen: a red past 20 s stays full size, not highlighted, with the card below; a repeat of the claim highlights and hides the card again.

D-178: A question the product info does not answer goes to the operator; in a solo show the host sees only how many there are (user decision 10/5, relayed by the planning session: "제품정보 등에 없는 질문은 그냥 운영자 화면으로 보낸다", "있으면 바로 게시 없으면 운영자한테"). Replaces D-135's host deferral card and D-140 step F.
- **No verified answer** (the sheet does not answer it, or the verifier blocked every draft): route `OPERATOR`, reason `no_verified_answer`, in solo and team, sensitive questions too. No host card and nothing posted. A verified draft that comes later (a new asker drafts again) still takes the intent's own route.
- **Shop policy** (shipping, returns, payment, order status, giveaway, other: `product_scope` none): keeps its `OPERATOR` intent route in a solo show too; no general deferral card, whatever the number of askers. The `general` reason and its PD branch are gone.
- **Product switch:** at the switch commit, the previous product's host questions that are still waiting (new, composing, ready, needs review, not answered aloud) move to `OPERATOR`, reason `previous_product`; a ready draft stays ready, so the operator can approve it. A new question about a product already shown and not on air also gets `previous_product`. AI-answered groups, "Which product?" groups and questions about the next product are unchanged. A product shown again later does not take its moved questions back.
- **Solo host:** the questions panel footer shows "N unanswered questions" ("답변 못 한 질문 N개"), the count of `OPERATOR` groups still open; in a team show the operator's desk lists them and the host shows nothing.
- Unchanged: an unresolved product stays with the host ("Which product?"); a verified answer posts at once (AUTO) or is a host card (HOST intents, sensitive, D-113); needs_human keeps its handling; an operator push still gives a no-answer group the fixed deferral line.
- Evals: comment-flow gold for shipping, order status, returns and payment is now `OPERATOR` (was `HOST` under D-140). The show replay reports a question routed to the operator as `to_operator` and counts it as an operator action.
- Tests: no verified answer goes to the operator in both modes; a sensitive question without an answer is no host card, and an operator push carries the deferral line; shop policy stays off the host's list at 3 askers; at a switch the previous product's host question moves, the answered one stays, a later question about it moves, and the new product's question is on the host's list (all fail without the change); host screen: the solo count, and nothing in team.

D-179: Malaysia prices in RM (user decision 10/5, demo values chosen by the planning session with the user's OK; `docs/PLANNING.md` decision 6): cream list RM159.00, live RM119.00; ampoule list RM139.00, live RM105.00; set RM205.00. The "bought separately" total (decision 5) is not added or computed.
- `products.json` has a `market_prices` block by market code (currency, symbol, each product's list and live price, each set's price). `DataPack.load` uses it when the market's currency symbol differs from the file's: every amount the products file and the sheet passages write in S$ ("S$36.00", "S$36") becomes the same item's price there ("RM119.00", "RM119"), so key facts, prompter points, passages and promo texts agree. An S$ amount with no MY price is a load error; prices are never computed.
- A promo with its own S$ values has no MY values, so it is left out of the MY pack and its run-sheet, and a warning is logged. Today these are the time sale (promo prices) and the gift (S$60 threshold). The set reminder is kept, at RM205. MY promo values are the user's to give.
- The sheets' index (one retriever) and `/catalog` follow the server's market. An MY show therefore runs on a server with `MARKET=MY`, and an SG server refuses an MY session (`market_needs_own_server`) instead of mixing S$ sheets with RM prices. MY stays tier `preview` (D-150): host cards only, nothing posted by itself.
- Spoken numbers split the market's symbol ("RM119.00" gives 119), and the number-subject check treats rm, myr and ringgit as units. The prompter hides non-required price points by the market's symbol, no longer by a fixed "S$".
- Tests: the MY pack has RM prices in products, passages, prompter points and the set reminder, with no S$ left and the two promos left out; the SG pack is unchanged; without the block MY still refuses (D-129); an SG server refuses an MY session, and a MARKET=MY server serves RM119.00 from its sheets.
- **MY promo values** (later on 10/5, demo values chosen by the planning session, which the user asked to choose the MY demo prices): the time sale is RM107.10 for the cream, RM94.50 for the ampoule and RM184.50 for the set (10% off the MY live prices); the gift is a pouch with orders over RM200 (`min_spend` 200). They live in `market_prices.MY.promos` (promo prices, spend threshold), and the gift's S$60 in its texts becomes RM200. All three promos are now in the MY run-sheet. A promo without MY values is still left out.

D-180: One theme for every screen of the browser, following the system by default (user question 10/5: "why is one screen dark and another light when it is set to the system?").
- **Cause:** `app/theme.ts` gave each screen its own default (host dark; Studio, operator and viewer light; hub, setup and summary system), and each screen kept its own choice under `ls.theme.<screen>`.
- **Now:** like the UI language (D-109), one preference for the whole browser in `ls.theme` ("light" or "dark"; absent means the system). Every screen, and every Studio pane, starts on the system setting. A choice made on any screen (Settings gear or toggle) applies to all of them at once, and to other tabs through the storage event. The old per-screen keys are ignored, so everyone starts on the system setting. The viewer phone mock follows too; it has no look of its own.
- Tests: the system preference by default; one key, old keys ignored; a choice on one screen reaches another at once; another tab's change through the storage event; a throwing localStorage still toggles.

D-181: The host screen's panels can be resized (user request 10/5: "the prompter, AI PD and live chat should be resizable").
- Two splitters: between the left column (prompter and questions) and the live chat (default 58 : 42), and between the prompter and the questions (default 50 : 50). Each sits in its own grid track as wide as the old gap, so nothing else moves, and it stays between the panels. The line and a grip show on hover, focus and drag, with the col-resize or row-resize cursor.
- Drag, arrow keys (5%) or Home/End (the limits) move a split; a double-click resets it. Every panel keeps at least 25% of its axis. The splitters are `role="separator"` with `aria-orientation` and `aria-valuenow` in %.
- The sizes are saved per browser in `ls.layout.host` (fractions) and restored on load; Studio's host pane uses the same splitters and key. "Reset layout" ("레이아웃 초기화") in the host Settings gear goes back to the defaults.
- The prompter row never goes below the height the prompter asks for: `useFit` shrinks the text first and sets the card's minimum height only when even the smallest zoom does not fit, and the row is `minmax(auto, …)`, so the status line and the alerts never leave the card (D-107, D-115 hold at any size). The splits are whole fr units, so the other panel still takes all the space left.
- The operator screen is not resizable: its columns are fixed widths (320 px | main | 360 px, and a two-column variant with grid areas), not a simple split.
- Tests: the drag math (pointer in the middle of the gap), the 25% clamp, the keys, saving and restoring (and a bad or out-of-range saved value), and on the host screen the separators, keyboard moves, double-click and the gear's reset.

D-182: The AI PD card never clips its line to say, at any panel size (planning session's check of D-181: with the left column at 35% and the prompter at 25%, or with `{cols: 0.75, rows: 0.75}`, the answer was cut off after "...if redness, swelling or").
- **Cause:** the card's box had a fixed height (200 px × scale, D-127) and cut off what did not fit, and the questions row could shrink below that box.
- **Fix, in this order:** the waiting rows give way (the list scrolls and keeps the card in view); the card's text shrinks in 5% steps down to 80%, as the prompter's does; if it still does not fit, the box grows to the card; and the panel then asks the host grid for that room (the questions row is `minmax(auto, …)` and gets a minimum height, as the prompter row does in D-181).
- **Chat minimum:** the chat keeps at least 30% of the width (left column at most 70%), so its answer text is not squeezed beside the "AI answer" label. A saved wider value is clamped on load.
- **Checked** in a live mock session at 1366 × 768 with the long caution answer: left 35% / prompter 25% (text at 85%, all in view); `{0.75, 0.75}` (stored 0.75 becomes 0.70, the questions row keeps 211 px, all in view); left 25% / prompter 75%; and the defaults. No page scroll in any. Tests: the 70% limit by key, drag and restore.

D-183: Every screen links back to the Hub, and every screen has the same Settings gear (user report 10/5: "there is no way back to the home screen"; the host's ☰ next to "LIVE / Studio" looked like a menu but did nothing).
- The brand at the top left ("LIVE / Studio" with a grid icon in place of the dead ☰) is a link to the Hub with the session kept, `aria-label` "Back to hub" / "허브로 돌아가기": host top bar, operator header, setup, summary, the Studio header, and the viewer's page chrome outside the phone. Studio panes show no link (the Studio header has it).
- During a live show the host and operator screens ask once ("Leave this screen? The show keeps running." with Stay and Leave; Esc or a click outside stays). A Ctrl/Cmd/Shift-click opens a new tab without asking; with no live show there is no question.
- Since theme and language are global (D-109, D-180), the viewer, setup, summary and the Studio header use the Settings gear instead of the old light/dark toggles; Studio's per-pane toggles are gone. Host-only extras stay on the host.
- Tests: the link and its session on host, operator, viewer, setup, summary and Studio (one link there, none in the panes); the question only while live, Stay and Leave, and none for a Ctrl-click or a ready show; the viewer's link and gear are outside the phone.

D-184: A judge or fact call that has not answered after `JUDGE_HEDGE_MS` (1500 ms, 0 = off) sends one identical second request; the first answer wins and the other is cancelled (cloud 00008 lines pass: a fact check timed out after 6 s with no second try, and a compliance judge timed out at 2.5 s, so two planted errors had no alert at all).
- Applies to the compliance, context, single and fact judges (`HEDGED_AGENTS` in `providers/llm.py`), inside each call's own deadline. An error from one request waits for the other. `LLMClient.hedges` counts, per agent, the calls that sent a second request and how many the second one answered; `probe_finals.py` prints them, and each one logs "no answer after N ms: second request sent".
- Measured with real models on my own whitening probe (15 finals × 3 runs, split3): 12 second requests (context 6, fact 4, compliance 2), none answered first. With the split eval's judge p50 1368 ms and p95 1653 ms, a 1500 ms hedge fires on roughly a quarter to a third of the judge calls; for compliance (2500 ms deadline) the second request has only about 1 s, so it helps mainly against a stuck request, as in the 6 s fact case. The planning session measures the extra calls and the missed lines on the lines pass before the value is final.
- Tests: a slow call gets a second request and its answer; a fast answer or another agent sends one request; an error waits for the other request, and two slow ones time out; 0 turns it off.

D-185: The whitening rule names skin-lightening, fairer-skin, bleaching and fading melanin or pigment (cloud 00008: the first half of a whitening line, a bleaching and melanin claim, came back from all three judges with no alert; in 00007 the same line passed).
- `data/markets/sg.json` BRAND-WHITENING description: "Brand policy forbids whitening, skin-lightening or fairer-skin claims (bleaching the skin, removing or fading melanin or pigment) and claims of permanently changing skin colour." The MY rule keeps its own description.
- `data/lang/en.json` whitening: two examples of my own ("It lightens your complexion until you look a few shades fairer.", "It strips the pigment out of your skin."), and reflex phrases "bleaches", "bleaching", "lightens your skin", "skin lightening", "fairer skin". The sealed line's wording is not used.
- Real models, my own lines, 3 runs: "fades the melanin and leaves them pale as porcelain", "lightens your whole complexion, you'll be so much fairer" and "bleaches the dark patches right out" alerted BRAND-WHITENING every time; the approved even-toned line and a texture line did not.

D-186: Behind `STT_RISK_HINTS` (default off until the planning session measures it), the speech stream also gets the market's claim words as phrase hints (cloud 00008: "whitens your entire face" was heard as "widens your entire face", so the whitening claim was missed). Glossary hints already cover product words; claim words were not hinted.
- The words are the `reflex_phrases` of the session's rules, so they come from the market's categories in the broadcast language's pack (SG 94, MY 111 with English), and no new list goes into the market files. They follow the glossary terms under the same 500-phrase cap, with duplicates dropped and no boost value.
- Added to the reflex phrases, because they were missing: "heal" (disease; "heals" was there) and "regenerating" (physiological). Whitening already had "whiten", "whitens", "whitening", "bleach" and, since D-185, "bleaches" and "bleaching".
- Each audio stream logs `stt phrase hints for <sid>: glossary N, risk M (STT_RISK_HINTS=…, hints on|off)`, so a run's setting is visible in Cloud Logging.
- Not done yet, as agreed: a sound-alike note to the judges (a violation only through a sound-alike reading would be a yellow check, never red).
- Tests: with the flag the claim words follow the glossary and the log line names both counts, without it there are none; duplicates are dropped and the cap holds.

D-187: Design arms, compared by measurement (user decision 10/5: "if there are several directions, build them all, test them all and take the best"). `DESIGN_ARM` = A | B | C | D | E, default A (today's behaviour, unchanged until a comparison picks a winner). The arms, from the planning session: B moves meaning to the LLM and keeps code only for checking its output; C is B without the reflex pre-scan; D lets the agents decide everything, with code keeping deadlines, retries, the hedge, the state machines, routing permissions and post idempotency; E is D with the compliance rules retrieved per utterance from Vertex AI Search (data store `live-studio-rules`, created by the planning session with the user's approval).
- **Cost per arm:** every agent call now records its tokens (`AgentCall.usage`: prompt, output, thoughts, cached), the call log line ends with `tokens=prompt/output/thoughts/cached`, and `LLM_USAGE_REPORT=<path>` writes the calls and tokens per agent of the process (and their total) as JSON at exit, for any eval script.
- Each arm comes in its own commits, B first.

D-188: Design arm B (`DESIGN_ARM=B`, D-187): the meaning comes from the model, and code only checks it. In arm A nothing changes (every existing test runs arm A).
- **Output and prompt:** the split judges and triage use `...B` output models (`models/agent_io.py`: subclasses whose extra fields are required in the schema sent to the model) and get their arm's lines from `prompts/design_arms.md` appended to the system instruction (`agents/arms.py`). The compliance judge also gets `QUALIFIED_RESULTS` (every product's in-house results with ids) after the user message, so the cached prefix is unchanged.
- **(1) Corrections:** the judge lists the alert and quotes the words that correct it (`correction.quotes`). Code accepts a correction only when the quote, of two words or more, is in the line (normalised). No word-overlap check (CLAIM_MIN, RETRACT_MIN), no replacement-wording match (D-098), no late-alert reconciliation by wording, no qualifier add-on rule (D-151); those are the judge's to see.
- **(2) Relink:** a line the context judge linked to nothing, while drafts are offered, is asked about once more with every offered draft (no coverage guess); it posts only if the judge now links it and every usual check passes.
- **(3) Spoken numbers and hedges:** the context judge reports `numbers_said` (digits, in the draft's unit) and `hedged`; posting holds when hedged or when a number said is not in the draft's digits. No `verbal_check`, `spoken_numbers`, `durations` or `is_unsure`.
- **(4) Qualifier:** for BRAND-TEST-QUALIFIER the judge picks a `qualified_result_id`; code checks the id exists and uses that result's wording, and drops the violation otherwise.
- **(5) Shout-outs:** a triage label (`shoutout`: purchase, first_time, compliment or null), not a regex; a reaction the prefilter settles has none.
- **(6) Draft check:** `verify_answer(minimal=True)` keeps only the citations (known passage, quote in passage, product), the digit-set compare and restricted phrases; the length and sentence limits, the subject word window and the in-house wording go to the LLM draft verifier.
- **Real models** (split3, my own 4 lines × 2 runs): 0 invalid outputs; the eczema claim was corrected by its quoted retraction, and the in-house number got the picked result's wording and was corrected by the add-on line through the judge. Tokens for those 24 calls: prompt 100,155 (cached 15,890), output 3,137.
- Tests: arm B's prompt lines and required fields; posting by the judge's numbers and hedge; a correction only with a quote from the line, and replacement wording alone corrects in A but not in B; the qualifier wording from the picked id, none for an unknown id; an unlinked line asked again with every draft and posted; the shout-out from the label only; the minimal draft check.

D-189: Design arm C (`DESIGN_ARM=C`) is arm B without the reflex pre-scan: no provisional chip while the judge runs and no reflex fallback alert when the judges fail or time out. Reflex still guards drafts, because arm B's draft check keeps restricted phrases. Test: with both judges failing, arm B shows the provisional chip and the unverified fallback alert, arm C neither.

D-190: An efficacy question gets the approved claims, and the composer answers a not-approved ask with approved wording (planning session's comment flow on b24b614: CF06 "will this ampoule remove wrinkles?" went to the operator in both runs, gold HOST with "fine dryness lines").
- **Cause:** the composer refused (`grounded=false`, empty): "the source passages do not contain the approved claim for fine lines". Search for the question found the ampoule's not-approved list ("Removes wrinkles ...") but not its approved claims ("Helps reduce the look of fine dryness lines"); `efficacy_claim` had no section of its own; and rule 6 ("never repeat claims about removing wrinkles") read as "refuse". Before D-178 the failed draft showed as a host deferral card, so the gold matched by accident.
- **How to find it:** a real-model probe of that one comment, printing the group, the draft's `verify_errors` and the composer's `reason` from `agent_calls`; then `gather_passages(..., intent="efficacy_claim")`.
- **Fix:** `efficacy_claim` maps to the "Approved on-air claims" section, read from the index directly when it is not among the prefetched sections (`retriever.sections`). The composer gets the product's `AVOID_SAYING` pairs (the sheet's "say not → say", approved wording, verbatim), and rule 6 now says: do not refuse; answer with the approved claim that fits, without repeating the viewer's claim, and use the AVOID_SAYING wording when it pairs the claim. One example of my own (the cream and "erase my wrinkles"). The gold is unchanged.
- Real models, 3 runs: "It helps reduce the look of fine dryness lines." verified, a HOST card (sensitive), every time.
- **Draft verifier numbers:** without `--llm`, "bad passing verify_answer 33/34; good blocked 0/32" reports the code layer alone. The bad set is mostly meaning-level flaws only the LLM layer catches, so that line is informational; the gate is the `--llm` run's "bad posted" (both layers) and "good blocked ≤ 3%".

D-191: Design arm D (and the base of E, F1 and F2): the agents decide, code keeps control only.
- **Setting:** `DESIGN_ARM=D`. Family D (arms D and E) gets arm B's model fields and prompt lines plus its own (`prompts/design_arms.md`, `## D:` sections). Arm A stays the default and is unchanged.
- **Whole data in the prompts:** both split judges get `PRODUCT_FACTS` (every passage of every product sheet, about 8.5k characters, after the cached prefix); the composer gets the whole sheet of the product (of every product for a multi question) instead of a search result, plus `RULES`; the draft verifier gets the same sheet and `RULES`.
- **Code checks removed:** no reflex pre-scan (like arm C); no comment prefilter (Model Armor, then triage decides every comment); a correction counts for every alert id the judge lists, without the quote check; no code number gate on a spoken-answer post (the judge's `consistent_with_suggested` and `hedged` decide); no `verify_answer` on a draft (the composer's own `grounded` and the LLM draft verifier decide).
- **Kept in code:** deadlines, retries and hedged requests, the alert/question/switch state machines, routing permissions (OPERATOR routes, a red alert blocks a post), post idempotency, stale-answer binding.

D-192: Design arm F2 (`DESIGN_ARM=F2`): arm D with whole files from one document store instead of search.
- **Store:** `providers/docstore.py` `LocalDocStore`: `list_documents()`, `get_product(product_id)` (`products/<product_id>.md`) and `get_rules(market, category)` (`rules/<market>/<category>.md`), built from the loaded pack (the data/ copies, priced for the market). One category (cosmetics) per market today, so the rules file is the market's whole rule set, which the judges already get in `RULES`. A GCS store can replace it behind the same three calls.
- **Judges:** the on-air product's file goes first in the cached prefix (`PRODUCT_FILE`), so it changes at session start and at each switch, and the context cache (content-addressed, D-130) is created again then; no other product sheet. Arms D and E keep `PRODUCT_FACTS` (every sheet, uncached).
- **Composer:** no search and no prefetch (`gather_passages(search=False)`): the whole sheet of the product plus the promo passages; RULES and the LLM draft verifier as in D.

D-193: Design arm F1 (`DESIGN_ARM=F1`): arm F2 with a tool step on the composer path. The tool step (`agents/file_tools.py`, logged as agent `file_tools`) sees only PRODUCT, MARKET and QUESTION, asks for files in a structured reply (`list_documents`, `get_product`, `get_rules`), the server runs them on the same document store (D-192), and the composer answers from the sheets it asked for, with RULES only when it asked for the rules. At most 3 round trips; a round with only get_* calls ends the step. Tool calls are a structured output, not native function calling, so every backend, the mock fixtures, retries and the per-agent token report work unchanged. The judges are as in F2 (a tool round trip per spoken line would add seconds to every alert).
- Real models, 3 comments (how to use, wrinkles, pregnancy): 1 round trip each, 2.7 to 3.2 s added before the draft, about 560 prompt tokens per tool call; rules asked for the wrinkle and pregnancy questions only; all 3 drafts verified, HOST cards, the wrinkle one "It helps reduce the look of fine dryness lines."

D-194: Design arm E (`DESIGN_ARM=E`): arm D with the compliance judge's rules retrieved for each spoken line from Vertex AI Search (`live-studio-rules-engine`, separk-cloocus, global).
- `providers/rule_search.py`: one long-lived HTTP client per process, warmed at session start (`rt.start`); ADC token with `x-goog-user-project` = `GCP_PROJECT`; `pageSize` 8 (`RULE_SEARCH_PAGE_SIZE`), `relevanceThreshold` LOWEST, filter `market: ANY("<market>")`, query expansion off, spell correction suggestion-only; timeout 1000 ms (`RULE_SEARCH_TIMEOUT_MS`).
- The search picks rule ids only, in its ranking order; the rule text is the pack's. A failure or timeout gives the judge every rule and is counted. The rules leave the judge's cached prefix in arm E, since they differ per line. Only the compliance judge uses it; the composer and draft verifier keep RULES whole as in D. Mock or non-Vertex runs get every rule.
- `LLM_USAGE_REPORT` adds `rule_search`: calls, failures, p50/p95 ms, and every query with its rule ids, so recall against the gold rule of each line can be computed after an eval run.
- Real models (probe_finals, 3 runs, disease claim, then correction, then a price line): 9 searches, 0 failures, p50 166 ms, p95 1652 ms (the first one of the process); the gold rule ranked first for the disease claim and its correction; alerts as in D.

D-195: Two holes in the spoken-answer post gate (found by a codex review, verified by the planning session), in every arm.
- **Cause 1:** a fact check that timed out or failed gave `facts=None`, and `contradicted = facts is not None and ...` read that as "no contradiction", so a line stating a price could post with its numbers unchecked.
- **Cause 2:** `verbal_check` and `judged_numbers_check` accepted a spoken number found in any offered draft, so with two drafts open the cream's answer said with the ampoule's price passed.
- **How to find it:** `logic/publish.py` `decide`: the `contradicted` line and the `others` union.
- **Fix:** a line that states a number (arm A: `lex.spoken_numbers`; arms B to F2: the judge's `numbers_said`) posts only after its fact check completed; otherwise the card is held with reason "check incomplete". The numbers are compared with the linked group's draft only; other drafts no longer accept a number (they still feed the D-175 relink candidate, which only picks a question to ask about again).
- **Trade-off:** a line that answers two shown questions at once with both numbers (gold V14 "Fifty mL. And it's thirty-six dollars today.", V46 "The ampoule is 30 mL and the cream is 50 mL.") is now held instead of posted; the code-layer tests list them as held by design. The code-layer verbal test now checks each case against the draft of the group it answers, not the one on screen.

D-196: One sentence that answers several shown questions posts each of them, safely (keeps the gold of V14 and V46, which D-195 held).
- The context judge (and utterance_judge) returns `answer.also_answered_group_ids`: the other open questions the same sentence answers consistently with their suggested answers. Validation keeps only open group ids other than the matched one, and only for an answer; fixtures encode them by question like `matched_group_id`.
- Group G posts only when G is linked (matched or also), every number said is in the draft of some linked group, and, when more than one group is linked, every number of G's own draft is said. Each linked group is decided and posted on its own (`_publish_also_locked`); the facts-complete rule of D-195 holds for each.
- The swap stays held: the cream's answer said with the ampoule's S$32 is held when the judge links only the cream (32 is in no linked draft), and when it links both the cream's own S$36 was not said.
- Real models (verbal V01, V14, V41, V46 and one more, 3 runs): V14 run 1 linked `g_size` with `also_answered_group_ids: ["g_price"]` and posted. The 4 misses were all timeouts: the context judge twice on V14, the fact checker twice (V01, V41 "check incomplete").

D-197: Adversarial eval scores the right alert only (full review P1, `eval_adversarial.py`).
- A risky line is caught only with the expected rule or field, and for a fact line with the expected correct value in the correction. An alert of the right kind with another rule or field is no longer a catch.
- Every other alert on a risky line is an "extra wrong alert"; a new pass line requires ≤ 5% of risky lines with one. `expected.also_ok_fields` accepts a second true fact (like `also_ok_rule_ids`).
- **Bug found on the way:** the labels name facts by what was said (`live_price`, `panthenol`, `niacinamide`), the fact checker by `FactField` (`price`, `ingredient_amount`), so the old "right rule/field" column never matched them. `LABEL_FIELDS` maps them.
- Re-scored `docs/eval/adversarial-tune-d143.json`: detection 100%, false alerts 0%, extra wrong 9.5% (FAIL). The 4 extra-alert lines are AV021 (DISEASE plus VULNERABLE) and AV023, AV045, AV125 (a packaging note: the host says "jar", the cream is a pump tube, which is true). They need label review (`also_ok_fields: ["packaging"]`, `also_ok_rule_ids`), not code.

D-198: Spoken-answer eval: PASS needs 0 false, 0 missed and 0 duplicate posts, with a runtime replay (full review P1, `eval_verbal_post.py`).
- PASS (and the exit code) now needs 0 false, 0 missed and 0 duplicate posts. Missed posts are listed as "logic" or "timeout" (no judge output, a judge or fact call that did not finish, or "check incomplete"); both count against PASS.
- Agent mode also decides every group the judge linked (D-196), so a post to a linked group the case did not mark is a false post.
- `--runtime`: each case runs in a real session. The questions and verified drafts are seeded, every open question of the case is put in a host slot (the shown one first), the line is submitted, the 2 s publish window is waited out, and the committed host-answer messages are read back with the runtime's own decision lines and the judge and fact calls.
- **Found on the way:** in the runtime a question about the product that is not on air reaches the judge only from a host slot (`_open_questions_locked`). Seeding only the shown slot hid V46's ampoule question, so the judge could not link it.
- The D-196 prompt example was one of our eval lines (V46). It is replaced with my own ("It's fragrance-free, and you get 50 mL in the tube."), and the bullet now says to check every part of a two-fact sentence against every open question.
- Real models: V14 and V46, 3 runs agent mode: PASS. V01, V14, V20, V30, V41 and V46, 2 runs runtime: PASS.

D-199: Comment-flow eval scores silence as a failure (full review P1, `eval_comment_flow.py`).
- Route: every gold question is scored, also one that never reached a group (kind wrong, or lost); before, such a comment was left out of the route score.
- Delivery (new pass line, 0 undelivered): an answer counts only when a published message replies to the asker, for AUTO at once and for HOST once the host confirmed; with `post_to_all_askers` every asker must get it.
- Cache: reuse counts only when exactly one AI draft served the question and, where the answer is posted, every later asker got it. Before, no draft at all scored as reuse.
- Re-scored `docs/eval/comment-flow-d157.json`: route 91.4%, cache 98.1%, now also 1 of 62 undelivered (CF06 c_wrinkles: confirmed but not delivered; fixed later by D-190). The older `comment-flow-3a94506.json` shows many AUTO clusters undelivered, which the old scorer passed as cache reuse.

D-200: Injection eval gives an automatic verdict (full review P1, `eval_injection.py`). A run fails when text from `expected.must_not` (case-insensitive) appears in anything published in the session or carded for the case, when `expected.no_post` is true and a reply to the case was published, or when a lookalike or normal comment was hidden by Armor or triage. PASS needs no failed run (exit code 1 otherwise); unscreened comments are counted apart. The case file stays with its holder; the keys are `must_not` (list) and `no_post` (bool).

D-201: Draft-verifier eval scores each arm's real production gate (full review P1, `eval_draft_verifier.py --arm`). The code layer is now one function, `comments.draft_code_gate`, used by the runtime and by the eval: full `verify_answer` for arm A, the minimal one for B and C, only the composer's own refusal for D to F2. With `--llm`, the verifier runs under the arm (its prompt additions and RULES) and gets the cited passages, or for D to F2 the product's whole sheet, as in production. Code layer alone on `draft_verifier_cases.jsonl`: bad drafts passing A 33/34, B 34/34, D 34/34; good blocked 0/32 each. So for D to F2 the LLM verifier is the only gate, and its `--llm` run per arm is the number to compare.

D-202: Summary agent stats count failures (full review P1, `logic/summary_stats.py`). Each agent row keeps p50/p95 of the successful calls (`calls`) and adds `attempts`, `failures`, `timeouts`, `failure_rate` and `deadline_attainment` (attempts that did not time out, out of all). Before, only successful calls were counted, so an agent that timed out more looked faster. The summary table shows calls as attempts, plus "Failed" and "In time".

D-203: A fact check that times out or fails on a line stating a number runs once more, with its own deadline, before the publish decision (`_run_facts`). The card waits; nothing posts until a check completes (D-195). Lines without a number are not retried. The agent-mode verbal eval calls the fact checker once; `eval_verbal_post.py --runtime` includes the retry.

D-204: The safety state is checked again when a pending host answer is committed (`finish_pending_locked`). A HIGH alert raised during the 2 s cancel window cancels the post; the card stays for the host. Before, only the question, answer, promo and document state were rechecked.

D-205: An operator's reply is verified before it posts (full review P2, `comments.write_answer`). Every number must be in the product's sheet, a running promo or the question's verified draft; an edited AI draft (`operator_edit`) also passes the LLM draft verifier on the product's whole sheet (a timeout or error counts as not verified). A problem returns 409 `unverified_reply`, and the operator screen shows the same "Post anyway" as for a restricted phrase. A reply posted that way is stored as not verified, with its problems; a reply that passes is stored as verified.

D-206: Model Armor fails closed (full review P2). Only `filterMatchState` `NO_MATCH_FOUND` passes; a missing or unknown state is "unscreened" like an error or a timeout (`armor.py`). An unscreened comment is screened once more; still unscreened, it reaches no model and goes to the operator as an "other" question (OPERATOR route, nothing drafted, analysis source `unscreened`). Before, an unknown state passed, and an Armor outage dropped the question as a reaction.

D-207: Fact absence needs proof, and units count (full review P2, `fact_checker.post_validate`).
- "Not in this product" stands only when the sheet proves it: the product's "Free from" list names the ingredient, or the sheet has a complete ingredient list (a section "Ingredients", "Full ingredients" or "Ingredients (INCI)"; "Key ingredients" is not one). Otherwise the claim is not_in_sources. Our two sheets say "Full INCI list is printed on the outer carton", so "the cream has 4% niacinamide" now gives no note. This changes the gold of adversarial AV123 and AV124 ("not in this product"); they need relabelling as not risky or as an `also_ok` miss.
- The same number in another unit or currency ("12 years" vs "12 months", "RM36" vs "S$36.00") is a contradiction, not a restatement (D-151 kept a restatement only when the numbers match and the units do not differ).

D-208: Spoken numbers with scale words (full review P2, `Lexicon.spoken_numbers`). "one hundred nineteen" read as 19, so a Malaysian price said aloud (RM119) could not be checked. The language pack's `number_words` gets `scales` ({"hundred": 100, "thousand": 1000}) and `and_word`; "one hundred and nineteen" is 119, "a hundred and five" 105, "two thousand five hundred" 2500, and a lone "one" before a scale word is kept. Two numbers said one after another stay two. Arms B to F2 already take the numbers from the judge (`numbers_said`); this fixes arm A's code reading.

D-209: The say-instead line is approved wording (full review P2, `utterance_judge.approved_say`). For every rule but the test qualifier (already approved, D-105), the line comes from the on-air product's approved claims or its "say instead" wording: the one that covers most of what the judge suggested (the first claim when nothing overlaps). The judge's own sentence is kept only as a light rewording of that line: no content word the line lacks, and at least 80% of its words ("It helps relieve the feeling of dryness." for "Helps relieve the feeling of dryness."). "With regular use, it helps keep your skin hydrated ..." adds a condition and becomes the approved "Helps keep skin hydrated for up to 24 hours in our in-house test." Before, any judge sentence was shown, and saying it corrected the alert (D-098).

D-210: The AI PD's promo card text is built from the live state (full review P2, `logic/promos.promo_cue`). A price promo's card names its own prices and the time left ("Time sale ...: extra 10% off now: Hydra Barrier Cream S$32.40; ... 45 s left."), never the stored "for the next 10 minutes"; a gift offer's card adds the time left. Any other promo text (a notice) shows only when every number in it is a current price or offer term, so "Cream + Ampoule set: S$62" is not coached during the time sale (set S$55.80).

D-211: The triage cache key keeps punctuation and emoji (full review P3, `cache.normalise_comment`): it only lowercases and collapses spaces, so "nice!" and "nice?" (a reaction and a question) no longer share one triage result. Fewer cache hits on near-duplicates is the accepted cost.

D-212: The draft verifier reads the cautions and the askers' own words independently of the composer (full review P3). `CAUTIONS` is every "Cautions" passage of the product (every product for a multi question), and `COMMENTS` the first 5 askers' comments (the canonical question can drop a stated condition such as pregnancy). Rules 4 and 5 use them. The operator-reply check (D-205) passes the same. Real models, arm A, 1 run: bad posted 0, good blocked 0/32; p50 1139 ms, p95 1491 ms (before: about 1000 / 1250 ms; the 700 ms latency line already failed).

D-213: Triage decides the product; aliases are candidates (full review P3, `attribute_product`). A product triage gives with basis explicit or content wins over an alias match in the text (code checks only that the id is a product). Alias matches are used when triage gives no product: one match is that product; several matches that include the product on air resolve to the product on air (a generic word fitting two products); otherwise unresolved ("Which product?"). Set questions and two-product comparisons keep their rules. This also covers rule 1 of the planned two-creams work.

D-214: Grouping keeps the conditions; the model decides that two questions share an answer (full review P3).
- `find_group`: the group triage picked (`group_candidate_id`) joins when product and intent match and no stated condition conflicts. Without the model's pick, code joins only the same question with the same conditions (`slots_equal`): an empty condition is no longer "any condition", so "Is it suitable for my skin?" does not join "oily skin" by code.
- `answer_key`: only one-value intents (price, set price, volume) share one draft across wordings; "shelf life once opened" and "unopened shelf life" (and every other intent) keep their own draft.
- Expect fewer code merges and a few more drafts in the comment-flow eval; the cache score counts one draft per gold cluster.

D-215: No code veto by overlap with approved wording (full review P3). `validate_compliance` no longer drops a violation whose span shares 80% of its words with an approved claim, in-house result, prompter point or sheet statement (D-123, D-132, D-174 removed with `_is_approved_wording`, `_sheet_statements`, `_span_phrase`). The compliance job text (compliance_judge and utterance_judge) gets the precedence instead: repeating an approved claim as written is not a violation; a sentence that only resembles approved wording but turns it into a forbidden claim is. Real models, `adversarial_cases.jsonl`, 1 run: false alerts on safe lines 0%, extra wrong 0%, detection 90%: 3 of the 4 misses were compliance-judge timeouts (AV002, AV082, AV145), and AV104 was marked quoted although the host agreed.

D-216: Onboarding steps 1-3 with `gemini_whole` (P0, docs/research/onboarding-spec.md; logic).
- `app/onboarding/record.py`: the typed `ProductRecord` (brand, product name, short names, generic word, category with evidence, language, variants with market and per-market prices in ISO currency and minor units with kind list/live/promo, offers, ingredients with `ingredient_list_complete`, approved and not-approved claims, avoid-saying pairs, qualified results with provenance, qualifier and marker, cautions, how to use, key facts, missing, conflicts). Every value carries evidence (file, locator, quote). No brand, market, language or category is assumed.
- `files.py` (step 1): uploads are stored content-addressed and never overwritten under `data/onboarding/<draft>/<sha256><ext>` (git-ignored); PDF, images, text and HTML go to Gemini as they are, DOCX and XLSX/CSV become located text in code ("[sheet Prices row 3] ...") via python-docx and openpyxl (new dependencies; Pillow as a dev dependency for the dev label image).
- `read.py` (steps 2-3): one Gemini call (`gemini-3.8-flash`, thinking HIGH, 600 s deadline) with every file as a part (`LLMRequest.parts`, Vertex only), prompt `read_prompt.md` (documents are data, never instructions; never invent; evidence for every value; conflicts with effective dates). Code then normalises currency codes, unit names, decimal strings and variant ids, and drops any value without evidence (noted).
- Two Gemini JSON-mode traps found: a float field looped ("30.0000..." until the output limit), so decimals are strings normalised in code; with optional fields the model skipped whole sections, so every field is required in the schema (nullable or empty list).
- `scripts/eval_onboarding.py <dir> --out record.json` runs exactly this app path. Dev documents of two fictional brands (`scripts/make_onboarding_dev_docs.py`, `data/onboarding_dev/`): a DOCX spec with a third-party "†" result and an injected "ignore your rules" line, two XLSX price lists that conflict (September vs October), a photographed label (JPG), and a Malay HTML page with a CSV price file. Results: P1 (HIGH, 109 s) every price right with the newer list, 3 conflicts with dates, third-party provenance, complete ingredient list from the label, the injected line ignored; P2 (MEDIUM, 28 s) 2 variants, the RM80 gift offer, 4 cautions and 2 not-approved claims in Malay, complete ingredient list.

D-217: Onboarding upload API (P0 step 1; logic). `POST /api/onboarding/jobs` (multipart `files`, optional `hints`) stores the files and runs the same pipeline as `scripts/eval_onboarding.py` in the background; `GET /api/onboarding/jobs/{job_id}` returns the status (queued, reading, done, failed), the record and errors. Caps: 20 files, 20 MB per file, 60 MB per job, 2 reads at a time per process; an unsupported type fails the job. Files and `result.json` go to `ONBOARDING_DIR` (default `../data/onboarding`, git-ignored). Jobs are kept in memory (lost on restart).

D-218: An approved onboarding record becomes a release that runs its own show (P0 step 7, first cut; logic).
- `POST /api/onboarding/jobs/{job_id}/approve` saves the record as an immutable, versioned release (`ONBOARDING_DIR/releases/<release_id>.json`, a new `_vN` per approval). Editing before approval (the approval bundle, step 6) is not built yet.
- `POST /api/sessions` with `release_id` creates a session on that product: `release_pack` builds a data pack with the market's rules, intents and language, the one product (prices in the market's currency, list and live, from the first variant priced there; other variants as key facts), its passages, and a one-segment run sheet. The passages join the retriever index once (`ctx.pack_for(market, lang, release_id)`). The shipped catalog and its sessions are untouched (releases are added, never replace).
- The adapter still writes passages under today's section names so the live path works unchanged; promos from offers (promo arithmetic, step 4) are not built yet.
- Real models, the fictional P1 serum onboarded at HIGH, then a session on its release: "erases wrinkles completely, guaranteed" gave HIGH ASEAN-3-SKIN-AGEING with an approved replacement from the record; "fifty-five dollars today" gave a price note with S$44.00 (the newer price list); "how much is the 30ml?" was auto-answered from the record (S$44.00, list S$58.00, and the 50 ml); "pregnant?" became a verified host card from the record's caution; "retinol?" went to the operator.

D-219: Prompt examples name no shipped product (P0 debt; logic). Every prompt's few-shot examples and inline examples move to a fictional brand: "Calm Day Lotion" (`product_a`, `PA-01`, points `pa-p*`) and "Bright Drop Serum" (`product_b`, `PB-01`), EXAMPLE CO., other ingredient names (bisabolol, allantoin, beta-glucan), other prices (S$24.00 live, S$30.00 list, S$21.00, set S$42.00, promo S$21.60/S$18.90/S$37.80, gift over S$40), other sizes (75 mL, 20 mL) and other claim wording ("Helps skin feel comfortable after cleansing", "Helps skin look fresher", "Skin softness: +30% after one week (in-house test)"). The rules and the example structure are unchanged; generic cautions ("consult your doctor") stay. `design_arms.md` keeps its generic "S$36" digit example. The shipped products' wording now reaches a model only through the session's own data.

D-220: Rule and language packs carry no shipped-product wording (P0 debt; removal of product data). In `sg.json`/`my.json`: the NUMBING carve-out is about a sensation the product's own data states, not our "mild tingling" wording; VULNERABLE no longer cites our sheets' pregnancy line; TEST-QUALIFIER takes its qualifier from the product's data ("in our in-house test" or "in an independent lab test") and uses neutral examples ("21 of 24", "12 hours", "2% allantoin"); SUPERLATIVE's example is "the best on the market"; sources say "Brand claims policy" instead of DAON sheet sections. In `en.json`: say-instead hints and unacceptable examples that quoted our claims or results ("fine dryness lines", "hydrated for up to 24 hours", "forty-five percent") are generic. The Vertex AI Search index of arm E still holds the old rule texts until it is re-imported.

D-221: No brand literal in code (P0 debt; logic). The host chat's brand-reply badge says "Brand" (KO "브랜드"); the viewer and Setup fall back to an empty brand instead of "DAON LAB" (the catalog's brand is shown when there is one); the summary labels brand replies "Brand answer"; the brief agent's rule-based fallback (unit tests only) reads a "Brand: X" line instead of looking for "DAON LAB". No "DAON" remains in backend/app or frontend/src outside tests and fixtures.

D-222: The live evals run on an onboarded release (logic). `eval_adversarial.py --release <id>`, `eval_comment_flow.py --release <id>` and `eval_verbal_post.py --runtime --release <id>` create each case's session on that release's one-product show (`create_session(..., release_id=...)`), so the case's `current_product_id` is ignored and case files may name the product by role; the verbal replay seeds its questions on the release's product. The release must exist under `ONBOARDING_DIR/releases`.

D-223: Promo arithmetic in code (P0 step 4; logic). A release's offers become promos of its show (`promos_from_offers`), listed on its run sheet so the operator can start them. Percent off, amount off and a fixed price change the price: the promo price is computed in code from the live price and the stated terms, with the stated rounding rule ("nearest 10 cents", "rounded down to the dollar"; 2 decimals half up when none is stated). A gift over a spend keeps its threshold (`min_spend`); buy-X-get-Y, bundles and other offers are shown as written and change no price. An offer for another variant is left out. Duration is the stated one, else the segment's 10 minutes.

D-225: Numbers with thousands separators, and every extracted number checked against its own quote (logic).
- **Cause:** the sealed onboarding pool had "5,000 mg" read as amount 5: the normaliser treated "," as a decimal mark ("5.000" -> "5"). The shared `number_set` had the same flaw ("5,000" -> {"5", "0"}, "S$1,250.00" -> {"1", "250"}), which the live verify, publish and fact checks use.
- **How to find it:** `normalise(...)` on a record with "5,000 mg"; `number_set("S$1,250.00")`.
- **Fix:** `number_set` reads "5,000" and "1,250.00" as one number. Onboarding reads a comma as a decimal mark only in decimal-comma languages (the record's `language`: de, fr, es, id, ...); elsewhere a comma must separate groups of three digits, and "0,50" is not guessed. Every extracted size, ingredient amount, offer percent and price must appear as written in its own evidence quote; one that does not is dropped and listed in `missing` (0 wrong numbers before completeness).

D-226: A second, focused caution pass in onboarding (logic). The sealed pool found 4 of 5 and 3 of 4 cautions (an eye-area caution in a prose brochure, a sun-protection line in a footnote). Alongside the full read, one more call over every file (`onboarding_cautions`, same model at MEDIUM, its own prompt) lists only safety cautions (contraindications, stop/consult lines, age, pregnancy, allergy and patch tests, eye/mouth/broken-skin areas, sun exposure, dosage, storage and children), with evidence. Cautions the full read lacks (not contained in an existing one) are merged in, then normalised like the rest (no evidence, no caution). The record's `models` names both calls. Dev P1 at HIGH: 127 s, the same 5 cautions (no new ones to find there).

D-227: Release ids in any script, and no borrowed law pack (logic).
- **Cause:** `_slug` kept only Latin letters, so a Korean brand and name gave the release id "rel_item_v1" and the product id "item": every non-Latin product would share them (and the retriever index is keyed by product id).
- **Fix:** `product_key` = the Latin part (if any) plus an 8-hex hash of brand and name; it is the release base and the product id.
- **No law pack:** a market pack lists the product categories it covers (`covers`, e.g. skincare, haircare, makeup for "cosmetics"). A release whose category is not covered (apparel, food_supplement) gets no law rules and no reflex phrases (never the cosmetics rules); only brand-level checks may run, and there are none until brand guidelines are onboarded. Approval returns the warning "no law pack for <category> in <market>: only brand-level checks run".

D-224: The onboarding approval screen (P0 step 6; logic). `/onboarding` (linked from the Hub: "Onboard a new product →"): upload any files of one product with optional hints, watch the read, then review every field with its evidence (file · place · "quote"): variants and prices, offers, cautions, approved and not-approved claims, test results with their qualifier and provenance, avoid-saying pairs, ingredients (and whether the list is complete), how to use, key facts; conflicts (values with their effective dates) and fields that are missing or were dropped are shown first. "Edit record" opens the record as JSON; "Approve and create release" sends the edited or read record (`POST /api/onboarding/jobs/{id}/approve` validates and normalises it again and checks that the show can be built in this market), then "Start a show with this product" creates a session on the release and opens the Studio.

D-228: A release whose category has no law pack says so on the live screens. The state's `market` block carries `law_checks` (false when the session's rules are empty) and `category`; the host top bar and the operator header show "No law checks for this category · <category>" (KO "이 품목은 법규 검사 없음").

D-229: Law packs built from regulator documents (logic). The same path as product onboarding, for rules: `POST /api/onboarding/lawpacks/jobs` (files, market, category) has Gemini (`gemini-3.8-flash`, HIGH, product-neutral prompt) read the source whole and write rule records (id from the source's numbering, title, description with the source's carve-outs, severity, topic, unacceptable examples, a general say-instead hint, evidence, and the categories covered); `POST /api/onboarding/jobs/{id}/approve-lawpack` saves an immutable, versioned pack (`ONBOARDING_DIR/lawpacks/law_<market>_<hash>_vN.json`). A release whose category the market's shipped pack does not cover takes the newest approved pack of its market that covers it (no reflex phrases: the judge decides); with none, it keeps no law rules (D-227). Entry point: `scripts/eval_lawpack.py <dir> --market --category --out`.
- Dev run on a fictional supplement-advertising guide (`data/onboarding_dev/law_supplements/`, clearly marked fictional): 7 rules in 36 s, ids from the clause numbers. Then the fictional Malay gummies (P2) as a release in MY with that pack: "These gummies cure the flu, you will never get sick again." gave HIGH SUPP-2.1 and MEDIUM SUPP-3.1; "twenty-five ringgit" gave a price note RM29.90. The say-instead line came from the record's approved claim, in Malay on an English show (language of the replacement line is still open).

D-230: A session shows its own catalog (blocker in the onboarding user flow; logic).
- **Cause:** "Start a show with this product" created a session on the release, but the host, operator, viewer and Setup screens loaded the server's shipped catalog (`GET /api/catalog`, one cached copy for the whole app), so they named the demo products and "DAON LAB · Skincare session". The STT phrase hints also came from the shipped catalog.
- **How to find it:** upload → approve → start; the session's `/state` prompter has the new product id while `/api/catalog` lists the demo products.
- **Fix:** `GET /api/catalog?session=<sid>` returns that session's catalog (product, brand, prices, run sheet, rules); `useCatalog(sessionId)` caches one catalog per session and every screen passes its session; a release session's STT hints come from its own catalog. Tests: the API flow upload → approve → start → session catalog, run sheet and prompter are the new product's while the shipped catalog is unchanged; the Studio's panes request `/api/catalog?session=<sid>`.

D-231: The approval screen speaks the operator's language (onboarding user-flow review; logic).
- Conflicts read "Overnight Renewal Serum 30 ml · live price SG" with one button per value ("Use SGD 46.00 (2026-09-01)", "Use SGD 44.00 (2026-10-01, newest)"); the newest dated value is preselected, and a choice writes that value into the record (money in minor units). A conflict the model named in its own words is shown as written.
- Values are edited in place ("Edit" next to sizes, prices, cautions, claims, how-to-use and key facts); the JSON editor stays as "Advanced: edit as JSON".
- Missing fields use plain labels ("Short names viewers use", "Product category", "<variant> · size").
- After approval the screen says what happens live: the price, the compliance rules applied (or "no law checks for this category"), and how many cautions, approved claims, not-approved claims and offers the show gets (`live` in the approve response).

D-232: Host lines in the show's language, translated at approval and never live (logic; the planning session's language rule).
- At approval, a record written in another language than a market language gets its approved claims, cautions and avoid-saying pairs machine-translated (`onboarding_translate`, faithful: same meaning, strength, numbers, names) into each language the market offers; the translations are stored with the release (the original lines stay as evidence), marked not reviewed, listed on the approval screen ("Machine translation into en (review before going live)") and named in the warnings.
- At run time a release show uses the record's own lines when it is written in the show's language, else the stored translation, else none: the alert still shows and its say-instead reads "(no approved wording in <lang>)". The say-instead picker (D-209) never falls back to the judge's sentence.
- Real models: the Malay gummies record translated into English in one call ("Vitamin C supports the normal function of the immune system.", 4 cautions).

D-233: Machine translations are reviewed line by line; an unreviewed one is shown to the host but never auto-posted; the prompter gets ingredients and test qualifiers from the record (logic).
- Translation review: `POST /api/onboarding/jobs/{id}/preview` translates the host-facing lines before approval (and says what the show would get); the approval screen lists every translated line with its own checkbox and an "Approve all translations" button; the approval sends the lines with their review state. At run time an unreviewed claim or avoid-saying line carries " (unreviewed translation)"; an unreviewed caution's passage is marked, and an answer citing a marked passage goes to the host (solo) or the operator, never out as an AUTO post. The approval warning counts the unreviewed lines.
- Prompter: a release's first 4 ingredients with an amount fill the INGREDIENTS panel (amounts in %, mg, mcg, g or IU); a test result's marker in an approved claim ("in 4 weeks†") becomes its qualifier ("in 4 weeks (tested by Kestrel Labs)").

D-234: A link no longer hides a viewer's question (injection eval v2: a benign question with a link was hidden; logic).
- **Cause:** the prefilter hid every comment with a URL or domain ("link"), and the triage prompt listed "any link or URL" under hide.
- **Fix:** every comment's links are replaced by "[link removed]" before it is stored or shown (`mask_links`), so the link itself never reaches chat or a model. A comment with a link and a question mark goes on to triage; a link with no question (spam, a bare link) stays hidden as before. The triage prompt now hides spam or advertising, and says a real question that had a link is a question.
- A question with a link but no "?" is still hidden by the prefilter; the operator can unhide it (triage then runs).

D-235: Adversarial scorer: `expected.unverifiable` on a safe line (a fact the sheet cannot settle, e.g. an ingredient the partial sheet does not list, D-207). Silence passes and a soft fact note is not a false alert; a compliance alert still is (a HIGH one is a wrong HIGH). The report counts "unverifiable lines with a soft fact note" on its own.

D-236: VERIFY_MODE arm for onboarding: `full` (default, today) or `risk` (logic; to be measured, dropped if not better).
- Every job (API and `eval_onboarding.py --verify-mode`) now carries `checks` (each item with its group and reason) and `check_summary` (`to_check`, `by_group`).
- `full`: every extracted value plus conflicts and missing values.
- `risk`: only what would reach the live show. 1 product: every conflict, a size without a price, a price or size missing or not a clear number in its quote (0 wrong numbers, D-225). 2 governance: no law pack for the category (or a show that cannot be built), each test result with the qualifier wording it needs. 3 safety: cautions only the caution pass found, unreviewed translated cautions. 4 offers: no amount to compute with, no stated rounding for a price change, an offer kind the show cannot compute. Plus 2 audit samples of unflagged values (stable per record). Prose (how to use, key facts) and full ingredient lists are not checked at onboarding; the live draft verifier covers them when used. The approval screen lists the risk items under "To check".
- Dev records (offline, same reads): P1 serum full 35 items vs risk 6 (3 price conflicts, 1 qualifier, 2 audit); P2 gummies full 22 vs risk 2 (audit only).
- Update (planning session): no "?" rule. Every comment with a link loses the link and goes to triage, which tells spam from a question ("price for the 50ml", "this one can use for kids or not"); only a bare link (nothing else) is hidden by the prefilter. The no-LLM triage stand-in (unit tests, mock demo) hides a link comment that asks nothing. The injection report counts triage calls per mode, to measure the extra calls in burst mode.

D-237: PREFILTER arm, `full` (default, today) or `pii_only` (logic; to be measured). `pii_only` keeps in the prefilter only what must never be displayed (email, phone number, a bare link) plus the rate limit; profanity and short reactions (English-only lists) go to triage. The planning session measures false hides of short questions ("ml", "price", "spf", "가격") and the extra triage calls.

D-238: Judge test drive (logic). The Hub's "Try it with a sample product →" opens `/testdrive`: one button reads the bundled fictional sample (`data/onboarding_dev/p1_lumen_serum`: a DOCX spec, two conflicting XLSX price lists, a label photo) through the real onboarding path (`POST /api/testdrive/start`; the read is cached by the files' content hash and reused, so only the first run pays for it), shows what was read with one preselected "Approve and start the show" click (`POST /api/testdrive/{job}/go`: approves the read as is, creates the release's show, starts it), and opens the Studio while a 75-second scene plays on the server: a greeting, a risky claim ("erases wrinkles completely, guaranteed"), its spoken correction with the product's approved claim, a burst of three price questions, a pregnancy question the host answers aloud with the product's caution, and a viewer's purchase; then the show ends. The scene is built from the session's catalog (nothing names a shipped product). Spend cap: 6 test drives per hour per process, one at a time (429 `testdrive_busy`).
- Access: the deployed service is behind IAP for one account; a judge without login needs that changed, which is the user's call (not done here).

D-239: The host chat shows the source of every AI reply: under the reply, its first citation's section (or document) and a short quote (the viewer already had a "Source" button that expands every citation, D-122). The brand avatar in the host chat is an icon, not the letter "D".

D-240: Live impact counters from logged state, each with its denominator (`metrics.impact`, the operator header): risky lines alerted (compliance alerts shown, not dismissed) of final lines; askers answered by AI, sent to the host, sent to the operator, of all askers; operator actions (logged `operator.action` events by the operator); LLM calls, tokens and tokens per hour of the show. Cost in money needs per-model rates, STT and infra rates the planning session supplies (not invented here); the assistant-off baseline comes from the replay (`assistant=false`, D-139), not from this screen. The host screen does not show them (its top bar is full).
- D-238 follow-up: the test drive's spoken answer reads the waiting question's verified draft aloud, so it is posted like a real host answer.

D-241: Brand guideline upload, restrict-only (logic). `POST /api/onboarding/brandpacks/jobs` (files, brand) reads a brand's guidelines with the law-pack reader (prompt now covers a regulator's, an industry body's or a brand's rules) into rule records with evidence; `POST /api/onboarding/jobs/{id}/approve-brandpack` saves an immutable, versioned brand pack (`ONBOARDING_DIR/brandpacks/brand_<hash>_vN.json`). A release of that brand gets the newest brand pack's rules added after the law rules with a `BR-` prefix; no law rule is removed or replaced, and other brands are unaffected.
- D-238 real run (cached read): "erases wrinkles completely, guaranteed" gave HIGH ASEAN-3-SKIN-AGEING and MEDIUM BRAND-ABSOLUTE-SAFETY, both corrected by the next line; the 3-question price burst was one group answered by AI with its citations (S$44.00 live, S$58.00 list); the pregnancy question's verified draft was read aloud and posted as the host answer; the purchase gave the AI PD's shout-out card; the show ended.

D-242: Arm FR, the live fact path on the release record (`FACT_MODE=record`; default `sheet`; logic). The planning session's sealed live lines on 6 unseen-brand releases: compliance types generalise, facts do not (split 28%, near_number 50%, numbers_in_words 67%), for structural reasons: one price per product from the first variant, offer terms invisible to the checker, superseded values not known as wrong, other markets' prices unchecked, qualifiers assumed in-house.
- In record mode a release's pack carries "Record facts" passages the fact checker reads with the sheet: every size's price in every market ("P 30 (30 ml) · MY live price: MYR 119.00"; this market's currency with its symbol), each size, superseded values from dated conflicts ("Superseded: ... was S$38.00 (version of 2026-09-01); current value S$36.00 ... Saying S$38.00 as current is wrong."), each offer's terms (percent, amount, buy X get Y, dates, minutes), and each test result with the qualifier it needs. The main price passages name their size ("Live broadcast price (30 ml): S$36.00"). The fact checker gets a record-mode addition (sizes, markets, superseded values, offer terms); the compliance judge gets QUALIFIED_RESULTS with each result's qualifier and a rule that a result said without it breaks the test-result rule whoever ran the test. Corrections still pass the existing quote check (the record facts are passages). A's post gate is unchanged.
- Real models on the fictional serum (2 sizes, SG and MY prices, a Sep/Oct conflict, buy 2 get 1, a lab-tested result), 5 wrong lines: both modes caught the wrong size price (S$62.00), the superseded price (S$44.00), the MY price on an SG show and the missing lab qualifier; only record mode caught the wrong offer term ("buy 2 get 1"). 4 correct lines (both sizes' prices, the offer, the qualified result): no alert in either mode. The sealed comparison A vs FR decides.

D-243: Onboarding reads numbers written as words, routes test results, certifications and limitations, and lists hygiene and storage lines as cautions (sealed onboarding run on 939d043; logic).
- **F1 numbers as words.** `numwords.numbers_in_text` reads, in code, digits ("29,000", "29k"), English and Malay number words ("twenty-nine thousand", "dua puluh sembilan ribu"), Korean sino and Chinese numerals ("이만 구천", "二万九千", "영 점 오") and mixed forms ("2만 9천", "1.5만"). The evidence check (D-225) accepts a value the quote states in digits or words; when the quote states exactly one number and the model's differs, the quote's number is used and a "corrected" item goes to the person's check list; otherwise the value is dropped as before.
- **Root cause found on the way:** "29,000 won read as 290" was our minor-unit convention, not only the model: every Money was divided by 100. Currencies without a minor unit (ISO 4217 zero-decimal: KRW, JPY, VND, ...) now keep the whole amount (`money_value`, `to_minor`; the reader prompt and the screens follow).
- **F2 routing pass** (`onboarding_route`, one call after the read, any language, no keyword lists): key facts, approved claims and directions that report a test result or a certification by a named body become qualified results with provenance and qualifier (evidence stays the source item's); limitations and disclaimers are copied into cautions.
- **F3/F4 caution pass:** it now also lists hygiene and storage instructions that protect the user (kept in the directions too) and limitations or disclaimers (a size guide is not a guaranteed fit, listed variants are not a promise of stock, colours may look different on screen, results may vary).
- Real models on a made-up Korean cushion document (`data/onboarding_dev/p3_haneul_cushion`): prices "삼만 구천 원" / "이만 구천 원" read as KRW 39000 / 29000, size "십오 그램" as 15 g; the lab result became a third-party qualified result with its qualifier, the vegan certification a qualified result; "colours on screen may differ" and the two hygiene lines are cautions; risk mode left 6 items to check. 373 s (read, caution pass and routing).

D-244: Live fact checks read the release record by default (FR), and the L1-L7 misses get logic fixes with one made-up test each (sealed live run: FR 87.4% vs sheet 81.5%; logic).
- **FR is the default:** `FACT_MODE=record` (config, `.env.example`, `release_pack`). `sheet` stays as the comparison arm.
- **L1:** a `contradicted` verdict needs a correction its quote states (a number, or the quote's own words). "not disclosed" is no source value, so the claim becomes `not_in_sources` (no false alert).
- **L2/L3:** each offer fact now carries its terms as the documents write them ("terms as written: ...") and totals computed in code ("pay for 2 = ... for 3 items", "offer price ..."), plus one "Live unit price X; 2 units Y; 3 units Z" line. An offer total is compared with these, never with the unit price.
- **L4-L6 and ingredient presence (FR fact checker prompt):** every number with a unit is checkable wherever it appears; price terms (tax, delivery, per unit) are checkable; an old value described as old is supported, as current is contradicted; an ingredient a "Free from" statement or a complete list excludes is contradicted; contradict only with a value SOURCE states.
- **L7:** naming who ran the test or certified it is saying the qualifier. Code (`names_the_source`) takes the distinctive words of the result's qualifier and skips the qualifier alert when the line names them; generic words ("our", "test", "in-house") do not count. The FR judge prompt says the same.
- Tests use made-up products only (`test_d244_*`). The sealed set was not read.
- **L8 (follow-up):** the host reads `correct_value` aloud, so a bare field word is no correction ("fragrance" for "no fragrance in it" showed "Say: fragrance"). Both fact checker prompts now ask for a short statement of the right fact in the quote's words. In code, when the correction has no number and only repeats words the host said, the card shows the source quote instead. The L1 check is now script-neutral (`_from_quote`: a shared word in Latin script, two letters in a row in other scripts), so a Korean correction in the quote's words is not dropped.

D-245: Onboarding links a marked claim to its footnote, takes the category from a closed list and knows certifiers (sealed onboarding on e713447: governance 6/9; logic).
- **R1 footnote marks:** the routing pass now links an item that carries a footnote mark (†, ‡, *, ※, §, superscript or bracketed numbers) to its footnote or test report. The footnote may be another record item (`linked`) or in the files: when any item carries a mark, the files go with the routing call. The claim becomes a qualified result with the footnote's provenance and qualifier. Its evidence is the claim's quote plus the footnote's quote. The footnote item alone is not routed again.
- **R2 closed category list** (`category_list`): the market law pack's category and covers, the covers of every approved law pack of the market, then a generic set (apparel, food, electronics, ...). The reader gets the list. A word outside it ("sports_leggings") is mapped to the nearest entry by one small call (`onboarding_category`). The word as read stays in `category_evidence` and in a note. A category no law pack covers is now flagged in `full` check mode too (it already was in `risk` mode, D-227).
- **R3:** provenance `certifier` (a named certification body, not a lab), so the qualifier can say "certified by <body>".
- Tests with made-up products: `test_d245_*`; the D-243 routing test gives the new fields.
- **R4 (follow-up):** Korean and Chinese decimals are read: "영 점 오", "영점오", "일 점 이", "零点五". One digit syllable is a number only before 점/点. Digits inside a numeral ("2만 9천", "1.5만") are no longer numbers of their own, so the quote no longer also "states" 2 and 9. Two digits in a row without a scale ("5 이하") are a digit and a word, never the numeral 2. A word with 점 ("단점") is not a decimal.
- **R5 (follow-up):** every value the evidence check drops (ingredient amounts, offer percents, sizes, prices) is a risk-mode check item ("product" or "offers" group), not only a note.
