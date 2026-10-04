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
