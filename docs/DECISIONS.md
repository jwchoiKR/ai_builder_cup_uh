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

D-246: FACTS_MODEL picks the fact checker's model (base and FR); empty means LLM_FAST_MODEL, so today's behaviour is unchanged. Together with FACTS_THINKING it lets the eval compare Flash-Lite MINIMAL, Flash-Lite LOW and gemini-3.8-flash LOW on unseen products (MINIMAL was picked on the two shipped products only). The model is warmed up at start and shown in /api/health (logic).

D-247: Arm FD (`FACT_MODE=docs`): the live fact checker reads the release's original files on top of the record (logic). Kill criteria were set before testing. On the same sealed set, FD is adopted only if detection is at least FR + 2 points, false alerts are 5% or less, and fact-check p95 is within the fact budget (3.0 s when the arm was set; the user later allowed 5 s for fact corrections). Otherwise FD is dropped.
- **What the model gets:** the files as onboarding read them (PDF, images and HTML as parts; DOCX, XLSX and CSV as text with locators), each after "FILE <name>". The system instruction and the files go into one Gemini context cache per release and model. The cache is made at session start (`FactChecker.warm_cache`). The product and retrieved-passage blocks stay in the message, because the retrieved passages change per line. Below the 4,096-token minimum for a Gemini 3 cache, the files are sent with every call, uncached.
- **Prompt (FR plus FD):** the record is an index and the files are the authority. A correction from a file sets `passage_id` to "file:<name>#<locator>" and quotes the file verbatim. With no source value there is no contradiction (L1).
- **Code (`onboarding/sources.py`):** each file has one "Source file" passage holding the text code can read from it (text, converted text, PDF text via pypdf, HTML without tags) plus the record's evidence quotes from that file. For an image, those quotes are the only text code has. The locator is cut off and the usual passage check runs: the quote must be in the file text, the numbers in the quote, L1.
- **Unchanged:** the record still drives the prompter, offer arithmetic, qualifiers and rule packs.
- **Logged per call (existing):** latency and prompt, output, thought and cached tokens (log line, audit and USAGE). There is no cost figure: the repo has no price table, and we do not make one up. Cost = tokens × the price the eval applies.

D-248: Code may overrule a fact-check verdict, but never in silence; the sealed FR run misses fixed in their general form (sealed live run on e1d6f82: average detection 87.0%, false alerts 1.9-9.3%; logic and one lexicon line of data).
- **Every code drop is logged** ("fact claim dropped by code: <reason> | field, stated, correct, passage"). In 3 of the 4 traced misses the model was right and code dropped its verdict in silence.
- **Presence (D-123 fix):** "contains fragrance" against "No fragrance ingredient is added", or "contains no fragrance" against "contains fragrance", is the opposite fact, not a less specific one. The less-specific rule now applies only when the host and the source agree on presence or absence (the language's absence cues).
- **Thresholds (D-151 fix):** "S$90" said as exact, against a correction or quote that words it as a threshold ("> SGD 90", "more than S$90", "exceeds"), is not a restatement. The language pack gets `comparison_cues` (data, en). The host is shown the source's words, not the bare number. Offer facts now name what an amount is (minimum spend, amount off, fixed price, bundle price) and the gift.
- **L1 tightened:** most of a word correction's value words must be in the quote (first five letters; framing words such as "given", "made", "claim" do not count). A stated number "corrected" by words alone ("24 months" against "No period after opening is given") is a value the source does not give, so it gets no alert. Ingredient presence is the exception ("2% retinol" against "free from retinol").
- **Test-result qualifier:** the qualifier rule now comes with the record's qualified results, whatever law pack the category gets. A supplement under a law pack built from documents never had it. `has_law` counts only the other rules, so the warnings about a missing law pack still show.
- **Revisions (FR prompt):** a line that describes the change between versions is supported when each value matches its own version.
- **FD cache:** the cache now also holds the product and full-sheet blocks. The fact checker gets whole sheets, not search results, so for a one-product release these blocks are the same on every line. The cache is warmed at start with the first product's exact blocks.
- Pipeline tests on made-up releases (`test_d248_*`), run through eval_adversarial.run_case.

D-249: Onboarding coverage audit: one pass lists what the files state and the record does not hold, and every item goes to the person's check list (logic).
- **Why:** a value the reader drops or never reads becomes a live miss that no fact check can catch (sealed run: a footnoted claim, a Korean decimal, offer terms). This is the general fix for silent drops (R4, R5) and missed links (R1).
- **How:** `onboarding_audit` runs after the record is final (read, caution pass, routing, normalising, category). It gets the files and the record JSON. It lists numbers, conditions (offer thresholds and their comparison, eligibility, limits, combinability, validity, markets), claims, test results, certifications and cautions that the record lacks or holds with a different value. Each item comes with file, locator, verbatim quote and the record's different value.
- **Code:** duplicates are dropped. Each quote is looked up in the file's readable text (`in_file_text`: true, false, or null for an image). A quote that is not found is marked for a closer check, but it is not dropped, because the model may have read it from layout code cannot see.
- **Checks:** a new group "coverage" in both `risk` and `full` mode. Each item reads "in the files, not in the record (record has X): <file> (<locator>): "<quote>"". If the audit call fails, one item says "coverage audit not run".
- Cost: one more file-reading call per onboarding (gemini-3.8-flash at MEDIUM thinking).

D-250: Fact checks read number words in corrections, each code drop names the check that failed (also in the eval rows), and an in-house qualifier is never "named" by the panel size or the hours (sealed run on 1d88a00: false alerts 1.9%, detection 85.2%; logic).
- **Number words:** "twelve months after opening" now states 12. The fact checks use digits plus the language's spoken numbers (`lexicon.spoken_numbers`) for the stated value, the correction and the quote. The L1 rule "a stated number corrected without a number" was dropping right corrections written in words.
- **Named checks:** the passage branch runs named checks: unknown passage; quote not in the passage; a number of the correction is not in the quote; L1 no value of the quote; L1 a stated number corrected without a number; an approved-claims passage. A drop logs the name of the check that failed. `eval_adversarial` rows get `dropped: [{reason, field, stated, correct, passage_id, quote}]` per case (through a context variable).
- **Qualifier:** `names_the_source` (D-244 L7) returns false for an in-house qualifier (the language's in-house or own-test pattern). In a script with capitals, only capitalised words of the qualifier (a lab's or body's name) count. "22 adults" or "8 hours" in the qualifier no longer counts as naming the source.

D-251: Quote numbers in any script's words, and a right number with a wrong term keeps its alert (sealed run on 93064de, FR, Flash-Lite LOW, 5 s: detection 88.9%, fact p95 about 2.2 s; 111 drops in 18 runs, 79 of them correct "field other" drops of compliance claims; logic).
- **Numbers in words in other scripts:** fact checks read numbers with onboarding's `numwords.numbers_in_text` as well. A quote such as "영 점 오 퍼센트" now states 0.5, so the correction "0.5%" passes the "a number of the correction is not in the quote" check.
- **Term disputes (L5):** "a stated number corrected without a number" is no longer a drop when the stated number is right and the correction is about a term attached to it, such as "S$36 per tube includes delivery" against "Delivery is not included in this price". The number counts as right when the quote's passage states it, or, for a price field, any passage of the product. A number with no source at all is still dropped, for example "nine months" against "No period after opening is printed".

D-252: An endorsed quote is the host's claim, offer combinability is a labelled term, an absence the quote does not state is no correction, and packaging in key facts is checkable (sealed FR run on 93064de; logic and one lexicon line of data).
- **Endorsed quotes:** the model's `is_quoted` flag turned the alert off (alerts.py, publish.py). `validate_compliance` now clears `is_quoted` on a claim that is not negated when the same line endorses it. The endorsement is found with the language's `affirmation_cues` (data, en: "and yes", "I fully agree", "that's true", ...). "I don't agree" is no endorsement, because a negation cue among the three words before the cue cancels it.
- **Offers:** the record's offers get `combinable` (yes/no/null) and `conditions` (exclusions, limits, eligibility, as written). The reader prompt asks for both. The offer fact line says "combinable with other offers or codes: no" and "condition: ...". Releases saved before this change still load (both fields have defaults).
- **L1 absence:** a correction worded as an absence ("No water-resistance claim is made") whose quote states no absence is the model's note, not a source value, so it is dropped. Ingredient and fragrance are the exception, because a complete list can prove an absence.
- **FR prompt:** packaging, form and texture stated in any passage, key facts included, are checkable.

D-253: FD file quotes are checked tolerantly, the test-result qualifier rule covers every provenance, and FD gets FR's compliance inputs (sealed, 93064de, Flash-Lite LOW, 5 s: FR 89.8% vs FD 91.3% detection, false alerts 2.8% vs 1.6%, fact p95 2.2 s vs 2.4 s; FD fell from 90.7% to 75.9% on a table PDF; logic and market rule wording as data).
- **Tolerant file quotes (`verify.quote_in_file`, "Source file" passages only):** both sides are flattened: Unicode NFKC, casefold, no whitespace, no line breaks, no table rule characters. A quote passes when it is a substring after flattening, or when a stretch of the file text around one of the quote's anchors (its longest numbers or words) matches at least 90% of the quote's characters in order and holds every number of the quote. Sheet passages keep the exact check.
- **Qualifier rule for every provenance:** the market rule BRAND-TEST-QUALIFIER (sg, my) is now titled "Test result without its qualifier". Its description covers in-house, laboratory, clinical, consumer panel and certification results, and says a generic mention that names no one ("testing confirmed", "according to the tests") is not the qualifier. The judges' prompt line no longer says "in-house result" only, and the FR compliance addition says the same. The code path (`approved_replacement`, `names_the_source`) already matched by numbers whatever the provenance.
- **FD gets FR's compliance inputs:** the compliance judge's QUALIFIED_RESULTS block and its FR addition were limited to `FACT_MODE=record`. They now also apply to `docs`.

D-254: `VERIFY_MODE=lean`: the risk items, at most 10 to check, the rest folded, and caution-pass cautions with a verified source accepted (sealed onboarding on fcfc870: 4 groups pass on 9 of 9, but 7-41 risk items per product read as a manual step; logic and screen).
- **Accepted:** a caution only the caution pass found is accepted when one of its evidence quotes is in the file's readable text (`quote_in_file`). It is listed as "added automatically, with source", not as a check. An image quote, or one code cannot find, stays a check.
- **Coverage:** duplicates are merged. Items whose quote the record's own evidence already quotes are dropped, unless the audit gives a different record value. The rest are ordered by live impact: conditions and test results, then certifications and cautions, claims, numbers. A quote code could not find goes last.
- **Product:** items of one field across variants become one item ("variants[*].prices… (12 variants)", or "8 variants: no price for this size", naming up to 6).
- **Audit:** one sample instead of two.
- **Cap:** the first 10 items by group order (product, governance, offers, safety, coverage, audit) are to check. The rest are folded. The summary gives `before` (the risk count), `collapsed` and `auto_accepted`. The onboarding screen shows "To check N of M found" with both folded lists.
- **Arm:** `VERIFY_MODE=risk` stays unchanged for the comparison; `eval_onboarding.py --verify-mode lean`.

D-255: FD becomes the default, with a 5 s fact budget; pack totals are computed in code; an absence note and a different substance are no corrections (sealed live run on fcfc870, 6 unseen products × 36 × 3, Flash-Lite LOW, 5 s: FR 94.7% vs FD 97.2% detection, false alerts 1.6% each, fact p95 2.3-3.3 s, no cache failures. FD clears its D-247 kill line; logic and settings).
- **Defaults:** `FACT_MODE=docs`, `FACTS_THINKING=LOW`, `FACT_TIMEOUT_MS=FACT_LATE_MS=5000`. A session without a release, or a release without stored files, behaves as FR. `record` and `sheet` stay as comparison arms. The compliance budget stays at 3 s.
- **Pack totals:** the record gets `Variant.pack_count`/`pack_unit` ("box of 10 bottles") and `Ingredient.per` ("per bottle"). The reader copies them and multiplies nothing. The pack count passes the same evidence check as every number. When an amount's basis is the unit a pack counts, a "Computed" fact line gives amount per unit × units in the pack. The prompt says to check a pack total against it, never against the amount per unit.
- **L1 absence, stricter:** an absence-worded correction for a field other than ingredient or fragrance needs the absence in its quote and at least 75% of its value words there. This drops model notes such as "Reapplication guidance does not imply …".
- **Substances:** for `ingredient_amount`, every name word the host gave must be in the correction, so "zinc gluconate" is not corrected by "zinc". The prompt says a compound is not its element, and an amount SOURCE does not give for that substance is `not_in_sources`.

D-256: The category is the regulatory product type, never the audience; the audience is `target_group`; an uncovered type maps to a covered one and is flagged (second sealed pool: a baby body wash read as "baby" ran with 1 rule instead of 15; logic).
- **Audience words removed:** "baby" is gone from the generic category list, and "pet" is now "pet_food". The reader prompt and the category pick say the category is what the product is (a baby body wash is body care), never who it is for.
- **target_group:** a new record field, with its own evidence ("infants", "children", "pregnant women"). It is copied to the live product and sent to the judges in CURRENT_PRODUCT. The compliance and single-judge prompts say that a safety, health or suitability promise to that group falls under the vulnerable-group rules.
- **Covered mapping:** when the category no law pack covers (`covered_categories`: the market pack's category and covers, plus approved law packs), one more small call maps it to a covered type the product is a kind of, or "none of these". The mapping is a note and a governance check item ("the category selects the law pack: confirm it"), in every check mode.

D-257: Onboarding keeps market limits, test conditions and offer edge terms, keeps archived values out of current fields, and lean never folds what the qualifier needs (second sealed pool, onboarding on e41fcf4: product 6/6, offers 6/6, governance 5/6, safety 80 of 84 by meaning; logic, mostly prompts).
- **Market and channel limits** (a price valid in one market only, online only, not sold in a market) are cautions. Both the reader prompt and the caution pass ask for them.
- **Test conditions:** `QualifiedResult.conditions` holds what the test holds under (indoor, dry skin, without meals, after N hours). The live say line becomes "<result>, <conditions> (<qualifier>)". The fact line adds "Holds only under: …". The caution pass also lists them.
- **Offer edge terms:** `conditions` keep their comparison words and edge cases as written ("exactly S$60 does not qualify", "two small sizes do not count as one large").
- **Archived values:** values from documents or sections marked archived, superseded or discontinued go only to conflicts with their dates. They never go to cautions, key facts, claims or other current fields, and the caution pass skips them.
- **Lean:** governance items, and items that share two or more words with a qualified result's statement or qualifier, are never folded. The cap of 10 applies to the rest.

D-258: A word of the result itself, or the qualifier's first word, never names the source (candidate e41fcf4, pool 1: "Testing confirmed SPF50+ PA++++" got no qualifier alert in 3 of 3 runs; logic).
- **Cause:** `names_the_source` (D-244 L7, D-250) took the qualifier's capitalised words as the source's name. "PA" in "… in SPF and PA protection tests" is capitalised and is also in the result. So any line that said the result "named the source", and the alert was skipped.
- **Fix:** the words of the result statement are taken out of the source words, along with the qualifier's first word, which is capitalised only because it starts the phrase. "labs", "laboratories", "tests" and "trials" join the generic words.
- **Tests (pipeline, made-up release):** "Testing confirmed …" and "… according to the protection tests" alert; "Larkspur Labs confirmed …" does not.

D-259: Pool-2 classes in general form: corrections in the show's language, offer-and-unit best prices, undated versions, threshold kinds, rejected quotes, unlisted ingredients, and negated cautions (candidate e41fcf4: pool 1 93.8%, unseen pool 2 72.5%, a 21-point gap; logic, one lexicon line of data, prompts).
- **Language:** the fact checker is told the show's language and writes `correct_value` in it; `quote` stays verbatim. The L1 word check is skipped for a correction translated from a quote in another script, but an absence-worded correction still needs its absence in the quote.
- **Offer and unit totals:** a multi-buy ("3 for S$60") is `fixed_price` with `buy` the count. Offer lines add "best price for N", the cheapest mix of the offer and single units, for N up to the offer's size + 2.
- **Undated versions:** a conflict without two dates now reaches the checker as "Versions of <field>: a / b (<note>). Only one is current". Before, only dated conflicts became "Superseded" lines. The FR prompt says "same as before" is checkable against versions.
- **Threshold kinds:** `comparison_kinds` (data, en: gt, ge, lt, le, eq) and `Lexicon.comparison_kind`. "at least S$40" against "above S$40" is no restatement; "over S$40" against "above S$40" is one. The prompt says S$40 itself does not qualify for "above S$40".
- **Rejected quotes:** a line that quotes a wrong idea and rejects it states the rejection (FR prompt).
- **Unlisted ingredients:** an ingredient is absent from the sheet when any of its words is missing ("pear juice" against "apple juice"). The complete list or "Free from" still has to prove it (D-207).
- **Negated cautions:** a new fact field `caution`. A line that tells viewers to skip or reverse a caution is contradicted with that caution as the correction, even when the line also breaks a rule. A compliance alert on a line that negates one of the product's cautions gets that caution as its say-instead line, not an unrelated approved claim (`negated_caution`).
- **Not changed:** usage intervals dropped by D-151 (item 5). The drop records are needed first.

D-260: Live-only fixes for the final pool-2 run: a result said in number words keeps its qualifier alert, compliance drops are logged, opposite polarity is no restatement, a failed compliance call is retried once, and availability is a fact field (candidate aa995d1: pool 1 93.2%; logic, prompt).
- **Number words in results:** `qualifier.approved_replacement` also reads the line's spoken numbers. "eight hours" matched no result, so the judge's BRAND-TEST-QUALIFIER was dropped as "matches no test result".
- **Compliance drops logged:** `validate_compliance` logs every violation it drops ("compliance violation dropped by code: <reason>") and adds it to the eval row's `dropped` list with the reason prefixed "compliance:". The reasons are an unknown rule, the line names our own test, it matches no test result, or it names the test's source.
- **Polarity (D-151):** a negation on only one side ("exactly S$40 qualifies" against "Exactly S$40 does not qualify") makes the same number a different fact.
- **Compliance retry:** in split3, a compliance call that times out, errors or comes back invalid is made once more, like the fact check (D-203).
- **Availability:** a new fact field `availability`. Channels (online only, retail counters) and markets with their limits are checkable.
- **Codes as names (item 4):** no change. `_same_substance` compares only Latin name words of 4 or more letters, so "CI 77491" against "CI 77499" is not dropped as another substance. A code swap reaches the alert.

D-261: A test result matches by the numbers its statement says, a word correction the line already says is a restatement, and a strict threshold with "not" agrees (candidate 947084e, pool-2 lip tint 55.6% to 79.6%; logic).
- **Result numbers:** `qualifier.result_numbers` = the result's numbers normalised ("8.0" is 8), plus every number its say line states before the qualifier, in digits or words. A release whose result held "8.0", or no numbers, matched nothing for "eight hours", so the judge's alert was dropped (D-116).
- **Word restatements:** a correction without numbers whose value words are all in the line, with the same polarity, is dropped ("available online only" against "Online only"). A negation on one side still makes it the opposite fact ("contains no fragrance" against "contains fragrance").
- **Strict thresholds:** with "above" or "below" (or > / <) on either side, "S$40 does not qualify" and "above S$40" agree. The polarity rule (D-260) applies only to exact or inclusive thresholds.

D-262: Two code drops of right verdicts found on the fresh third pool are fixed: a correction that leaves out the substance name, and multiplicative words (pool 3, fbb8aa7, the first and only clean run: 84.6% detection, false alerts 3.1%, fact p95 2.3-2.9 s, which matches pool 2 at 83-84%; logic and one lexicon line of data).
- **Substance names (D-255 refined):** when the correction names none of the host's substance words ("10% by weight"), the quote must hold them ("shea butter: 10% by weight"). When the correction names some of them, it must name all of them, so "zinc gluconate" is still not corrected by "zinc".
- **Multiplicative words:** `multiplicatives` (data, en: once, twice, thrice) and `Lexicon.times_numbers` feed the number reader every fact guard uses. "Brush three times daily" against "Brush twice daily." is no longer a "stated number corrected without a number".
- Any pool-3 number measured after this commit is "after fixing code drops found on pool 3", reported next to the clean 84.6%.

D-263: Onboarding state lives in Cloud Storage when `ONBOARDING_GCS_BUCKET` is set, and `VERIFY_MODE` defaults to lean (user option A, 10/6 morning: Cloud Run scales to zero and kept ONBOARDING_DIR in the container, so uploads, releases and packs were gone after an idle period or a redeploy; logic, deploy).
- **Source of truth:** with a bucket, every file onboarding persists is written to the local dir first and then through to `gs://<bucket>/onboarding/<path>` (`onboarding/storage.py`). That covers stored uploads, `files.json`, job `result.json`, `releases/*.json`, `lawpacks/*.json`, `brandpacks/*.json` and the test-drive cache. At start, every JSON object is read back into the local dir, so the existing listings (release versions, `lawpack_for`, `brandpack_for`) work after a cold start. An uploaded file is read back when it is first needed (FD's `release_sources`). A job still being read when the instance stops may be lost; approved artefacts are not.
- **Write-once:** releases, law and brand packs, and the content-addressed uploads are written with "create only" (GCS `if_generation_match=0`). The same bytes again are accepted; other content under the same name is refused (`storage.Immutable`).
- **Without a bucket** (tests, local evals) nothing changes.
- **Deploy (`deploy/cloudrun.sh`, idempotent; the user runs it):** the script creates `gs://separk-cloocus-live-studio-onboarding` in us-central1 if missing, enforces uniform bucket-level access and public access prevention, grants `roles/storage.objectAdmin` to `live-studio-run` on that bucket only (not project-wide), and adds `ONBOARDING_GCS_BUCKET` and `VERIFY_MODE=lean` to the env vars. `google-cloud-storage` is now a direct dependency.
- **Tests:** a memory bucket covers write-through, read-back on a new disk, listings, read-back on a miss, write-once and versions that continue. A pipeline test runs onboard, approve, a new app on an empty disk with the same bucket, then `POST /api/sessions {release_id}`.

D-264: The approved products are listed, so a show can start from one after a cold start (follow-up to D-263; logic and screen).
- **API:** `GET /api/onboarding/releases` reads the releases on disk (in the cloud, read back from the bucket at start). It gives one row per release: release_id, product name, brand, category, markets, approved_at and version, newest first.
- **Screen:** the hub's hero shows a "Previously approved products" picker with a "Start a show" button. It creates the session from the picked release and opens the Studio. The picker is hidden when there are no releases.
- **Tests:** the D-263 pipeline test now lists the release on the cold instance and starts the session from the listed id; a hub test picks a release and lands on the Studio.

D-265: Approval runs the BriefAgent on the release: an STT glossary and prompter points for an onboarded product (user-approved; logic, prompt, eval entry point).
- **Why:** a release's show had the approved claims as prompter points (the first one required) and a glossary of only its brand, product and up to four ingredient names. New names got few phrase hints, so chirp_3 would mishear them. The live evals feed text, so this never showed in the numbers.
- **What:** `onboarding/brief.py` builds a sheet from the record (names, ingredients, approved claims, test results with conditions and qualifiers, cautions, offers with conditions, directions, key facts, claims not approved). It then adds each source file's readable text and runs the BriefAgent with a release addition: the glossary keeps original spellings, with spoken forms in the show's language plus sound-alikes; up to 10 points in the show's language, each at most 140 characters, with qualified claims and must-say cautions marked required. The existing post-check still drops terms the document does not contain and points with restricted wording.
- **Stored:** `briefs/<release_id>.json`, write-once and mirrored to the bucket (D-263). A session from the release puts the brief's points on the prompter; the run sheet's required points are the brief's required ones. Its STT phrase hints are the brief's terms and spoken forms first, then the brand, product and ingredient names.
- **On failure** the release keeps today's behaviour and the approval returns a warning.
- **Settings:** `BRIEF_MODEL` (empty means LLM_QUALITY_MODEL) and `BRIEF_THINKING` (MEDIUM).
- **Eval:** `scripts/eval_brief.py --release <id> [--thinking X] [--model M] --out <json>` runs the same function and writes the glossary, the phrase hints a show would get and the prompter points. It stores nothing.
- **Real model, dev serum (made up), gemini-3.8-flash MEDIUM:** 31.6 s, 19 terms with sound-alikes, and 8 points: the lab-qualified claim, three caution points and the directions in English. Approval now takes about 30 s longer.

D-266: The release brief runs in the background after approval (follow-up to D-265; the test drive must not wait about 30 s more; logic and screens).
- **Approval** returns at once with `live.brief = {"status": "running"}` and starts the BriefAgent as a background task. When the brief lands, it is stored (write-once, D-265) and the cached show pack of that release is dropped (`AppContext.forget_release`), so the next show is built with the brief's points.
- **Status:** `GET /api/onboarding/releases/{id}/brief` returns done (the stored file), running, failed (…), or none (approved before D-265, or approved by another process). The release list carries the same `brief` field.
- **A show started before the brief lands** keeps today's points (the approved claims). Its STT hints come from the brief once the brief exists when the microphone connects (`release_phrases` reads the file at connect).
- **Screens:** the approval panel and the hub's release picker show the status, and look again every few seconds while it runs. A running brief shows the note "still running, about 30 s; a show started now uses the approved claims as points".
- **Test:** an approval that returns before a slow brief; a show started then has today's points; the next show after the brief lands has the brief's points.

D-267: The onboarding model is a setting, so gemini-3.1-pro-preview can be measured against gemini-3.8-flash as an arm (user asked 10/6; not decided: the default stays gemini-3.8-flash until the same evals pick one; settings only, 406beb5).
- **Settings:** `ONBOARDING_MODEL` (gemini-3.8-flash) and `ONBOARDING_THINKING` (HIGH) set the product read and the law and brand pack reads. `ONBOARDING_PASS_MODEL` and `ONBOARDING_PASS_THINKING` set the caution pass, field routing, category pick and coverage audit; empty means `ONBOARDING_MODEL` at each pass's own level (MEDIUM, and LOW for the category pick). The live path and the BriefAgent (`BRIEF_MODEL`, D-265) do not change.
- **Model id:** `gemini-3.1-pro-preview` on the global endpoint; the plain id returns 404, and it rejects MINIMAL thinking (docs/VERIFIED.md).
- **Eval:** `scripts/eval_onboarding.py --model --thinking --pass-model --pass-thinking` override the settings for one run. The result's `models` field names the model and level of every step, now including the category pick.
- **To decide:** run pools 2 and 3 (12 products) on both models with the same code. Compare the onboarding group scores (`score_groups.py`), safety by meaning (critic), check counts, seconds and tokens. Pro is only worth its cost and time if it lifts the groups or cuts the checks.

D-268: The compliance judge has its own deadline per try, `COMPLIANCE_TIMEOUT_MS`, as an arm: 2500 (today) against 3500 (planning session, 10/6; not decided; logic, setting).
- **Why:** on two made-up onboarded products, up to 7 of 60 row-runs got no compliance verdict at all because both tries ran out at 2.5 s. A line with no verdict can only raise a red alert through the reflex fallback (§8.4.3). Answered calls took 1.1-2.3 s, close to the deadline. The eval runs 4 cases at once, so these rates likely overstate a live show.
- **What:** `COMPLIANCE_TIMEOUT_MS` (0 = `JUDGE_TIMEOUT_MS`, so the default is unchanged) sets the compliance call's deadline in split3. The hedge (`JUDGE_HEDGE_MS`, 1.5 s) and the one more try (D-260) are unchanged. A verdict that comes back before 2.5 s lands exactly as today; with 3500 the first try's two requests get one more second before the second try starts. The slowest possible verdict moves from 5 s to 7 s. The context judge, the single judge and the fact checker keep their deadlines.
- **To decide:** pools 2, 3 and 4 on the same code with 2500 and 3500. Report detection, the rate of lines with no compliance verdict, and red-alert p95 from line end against the 3 s pass line.
- **Also tried and dropped (no code change):** a judge-prompt line for the critic's test ("would the rule forbid the wording if the line's facts were true?"). On made-up releases, 10 runs each, the HIGH on a "children can apply it on their own" line stayed at 10/10, so it was reverted after two rounds. The judges' reasons echo the D-256 target_group bullet ("a safety, health or suitability promise to that group"); whether "suitability" belongs there is with the critic.

D-269: Brief offer points carry every term, as an arm: `BRIEF_OFFERS` "sheet" (today) against "terms" (planning session's blind brief grading, 10/6: 0 of 17 offer points kept all their conditions; logic, prompt addendum, setting).
- **Why:** the brief's sheet listed an offer as its title, its free-text conditions and an amount. Percent, dates, combinability, gift and buy/get were left out, and a point could hold at most 140 characters. A host who reads an offer point without its conditions states an offer wrongly on air.
- **What ("terms"):** each offer line in the sheet is the fact checker's offer text (`record_facts`: percent, amount and its label, gift, combinability, conditions, dates, duration, the terms as written) with its id in brackets. The addendum asks for one required point per offer, with `source_section` "Offer <id>", that states every term. Code lets an offer point be up to 240 characters; other points keep 140.
- **Made-up release (lip balm with a code offer of five conditions, gemini-3.8-flash MEDIUM, one run each):** "sheet" dropped "not combinable" and marked both offers not required; "terms" kept every condition of both offers and marked them required. Both took about 23 s.
- **To decide:** the same blind grading on the sealed releases (offer points carried fully, any wrong point, seconds). Not done here: a code check that each offer's terms appear in its point (terms are in the documents' language, points in the show's), source ids on every point (B3), cautions coverage (B2) and the qualifier check on points (B4).

D-270: The judges' target_group bullet is an arm: `VULNERABLE_WORDING` "d256" (today) against "split" (the critic's ruling, 10/6: an age band or a usage direction that matches the documents is not forbidden, so the judge must not raise a vulnerable-group alert on it; whether it matches is the fact checker's job; prompt, setting).
- **Why:** pools 2 and 3 had wrong HIGH alerts on age and supervision lines for food and children's products. The judges' reasons echoed D-256's "a safety, health or suitability promise to that group", and they did so even when the release had no target_group.
- **What ("split"):** at load, the D-256 bullet in compliance_judge, utterance_judge and judge_single is replaced by `design_arms.md` "VS: target_group". The new bullet allows saying who the product is for, which ages may use it, and a usage direction. A safety or harmlessness promise to a group with or at risk of a condition, a claim that it helps or suits their condition, and "no medical check needed" stay under the vulnerable-group rules. The skin-type bullet and the "check with your doctor" bullet are unchanged. Prompt versions get "+vs", so the audit log shows the arm.
- **Made-up releases (a hand gel on the base pack; a vitamin C tablet on the fictional supplement pack), gemini-3.5-flash-lite, 10 runs per line:** on 7 age or direction lines, HIGH fell from 64/70 to 7/70. On 8 promise lines ("safe for kids", a no-side-effects promise, an eczema claim, a rash cure, "pregnant women can take it", "no medical check needed", "harmless for toddlers"), recall stayed at 80/80 on both arms. The 7 remaining HIGHs are one line, "children can rub it in on their own, no adult needed", on a product whose caution asks for adult supervision. Four probe lines share wording with the bullet's own examples; the three paraphrases ("aged five and over", "teenagers can take it by themselves", "harmless for toddlers") behaved the same.
- **To decide:** pools 2, 3 and 4 on both arms. Report wrong HIGH and promise recall separately. Kill rule (critic): if promise recall drops after one small patch, scrap it.
- **Seen on the way, not changed:** on the supplement, "For children 4 and up" got a fact caution note in 10 of 10 runs on both arms, although the documents say "not suitable for children under 4". That looks like a fact-checker false alert on age bands, a separate class.

D-271: An age band that states a caution's own range is no contradiction, and "40 and above" is "at least" (found on a made-up release while measuring D-270; logic, one lexicon line).
- **Why:** with the caution "Not suitable for children under 4 years.", the line "For children 4 and up" got a fact alert in 10 of 10 runs, while the fact checker's own reason said the two agree. Code kept the alert because it did not read "and up" as a threshold or "not … under 4" as the range "4 and up". It also read "under 4" as a restatement of that caution, which drops a true contradiction.
- **Range kinds:** a negation that comes before the threshold, with no number before the negation, turns the threshold round: "Not suitable for children under 4" means 4 and up, and "no more than 2" means at most 2. "S$40 does not qualify (above S$40)" is unchanged, because a number comes first (D-261). `_threshold_differs` compares these ranges. `_polarity_differs` leaves a negated threshold to that comparison.
- **Longest phrase:** `Lexicon.comparison_kind` takes the longest matching phrase, so "40 and above" is "ge" and no longer the "gt" of "above". In the en data, "and up", "and over", "or over", "and older" and "or older" are "ge". "And under", "or under", "and below", "or below", "and younger" and "or younger" are "le". Other languages still have no age-band words.
- **Made-up supplement, 5 runs:** "For children 4 and up" lost its false alert in 5 of 5 runs, each logged as a D-151 drop. "Not for children under 4" got no alert. "Fine for children under 4 too" and "For children 2 and up" kept their fact alerts in 5 of 5. "Fine for children under 4 too" still got a SUPP-3.3 HIGH on the split wording (D-270), which is the vulnerable-wording class and not this one.
- **Patch 1 (the one allowed round; blind grading on 0970386, 9 sealed releases with 10 offers):** "terms" beat "sheet" on all 9 products. Offers carried fully: 6/10 against 0/10. Missing conditions: 7 against 40. Two problems remained: one point widened "combinable only with the spend gift" to "combines with other offers", and four points of 34-41 words were too dense to read aloud. Now each offer gets 2 or 3 required points, in this order: what you get; when and where; limits and what it does or does not combine with. Each point is one spoken sentence of about 25 words, with no slashes or symbols. What an offer combines with is said exactly as the terms are written, never widened. Offer points add up to 3 per offer on top of the 10 points. `offer_misses` logs each offer condition that its points do not carry ("brief offer condition not in its points"), but only when the record and the show share a language; nothing is dropped. `eval_brief.py` writes the misses to its output.
- **Made-up lip balm, 5 runs:** every condition of both offers reached the points in every run. Points ran 10-24 words, and "not combinable with member prices or other codes" was kept word for word. Before number words counted, the check reported three false misses ("thirty" for 30). It reported none afterwards. Times were 13.7-50.8 s, and one run came close to the 60 s brief deadline.
- **Patch 1 scrapped (blind grading, v1 "terms" 0970386 against the patch 9aa66d4, the same 9 releases):** v1 was better in 6, the patch in 1, and 2 were ties; full offers were 5 against 5. The patch wrote 3 points that widen an offer and 2 that narrow one, and on 3 products it pushed cautions out. Its code (2-3 points per offer, `offer_misses`) is removed. "terms" is v1 again. The default stays "sheet".

D-272: The brief's offer points are built in code from the record, as the arm value `BRIEF_OFFERS=code` (scrap and rebuild after D-269's patch failed its kill rule; logic, setting).
- **What:** the model is told to write no offer point; any point it still files under an offer section is dropped and logged ("brief point dropped by code"). After the model's points, so claims and cautions are never pushed out, each offer gets points from its own record fields in a fixed order. First, what the viewer gets: the title, then percent, amount with its kind, buy/get and gift when the title does not already say them. Second, "Valid from … to …", with ISO dates read aloud ("1 November 2026"). Third, "Terms: …": each condition as written (one the title already says is left out), then the record's combinability unless a condition words it, cut into points of at most 140 characters between conditions. Nothing is generalised; offer points are not required.
- **Codes:** the record has no code field. So a code (capitals with a digit, "SAVE10") that the offer's evidence quotes hold and its fields do not is added ("code SAVE10").
- **Language:** the sentences are English. When the show or the record is in another language, one translation call (the D-232 prompt) turns them into the show's language. A translated line is kept only if every number and code survived; otherwise the English line stays, and that is logged.
- **Made-up lip balm, 5 runs:** both offers kept every condition and the code in all runs. The wording was the same every time, since it is code. Claims, cautions and directions came first. Times were 18-34 s against 14-51 s for the D-269 patch.
- **Measure:** the same 9 releases, blind against "sheet": offers carried fully, wrong points (widening is critical), anything pushed out, time.
- **Blind result (dc3d2b0, 9 sealed releases with 10 offers):** offers carried fully, code 8/10 against sheet 0/10. Cautions missing: 22 against 26, so nothing was pushed out. Better: 4 each, 1 tie. Code also wrote 5 wrong points, all from the template, 3 of them widening: the combinable yes/no printed where the terms allow combining with one named thing only; a gift with purchase rendered as "buy 1, get 1"; "minimum spend 40 SGD" for "above S$40". The points were also hard to read: timestamps, key: value phrases and repeated dates.
- **Patch 1 (kill rule: zero widening, no new lost caution, full offers not below 8/10):** the combinable field is never printed; a condition that names what an offer combines with is printed as written. The offer's kind decides the wording, so only a multibuy says "buy N, get M" and a gift reads "get a free <gift>". A spend threshold keeps the comparison its own quotes use ("above S$40", "S$40 or more"); without one it reads "the S$40 spend in the terms", never a comparison of our own. Dates are said once ("from 1 to 31 October 2026") without times, and the date line is left out when a condition already gives the dates. Money is said as "S$4" or "RM119". A value the title or a condition already says is not repeated. A condition that is a note about the document itself is still printed as written, so that case is open.
- **Patch 1 passed its kill rule; `code` is the default (blind, the same 9 releases, 9cae234):** offers carried fully, code 8/10 against sheet 0/10. Widening: 0. Safety cautions missing: 23 against 27. Blind better: code 8, sheet 1. The one wrong point ("remains S7.50") came from a source document that lost its "$" (a corpus defect). Amounts are printed only from the currency and number fields, never from a quote.
- **Readability round (f011115, no new arm):** each offer gets one headline line, which carries its dates, and at most two terms lines. A date or amount that the title or a condition already says is not said again; numbers are compared as values, so "S$4.00" and "S$4" count as the same. An English condition that starts with its verb gets a subject ("It is not combinable with codes"). The model lists, in the new `BriefOutput.document_notes`, the offer terms that only describe the document; code drops those conditions and logs each one ("brief offer term dropped by code"). In a point, an acronym with no spoken form stays in the glossary only, and the addendum now says so for every brief.

D-273: A product with no approved claim keeps its fallback alert (sealed pool 4, f23d635: a release whose documents state no benefit claim lost 84 of 108 row-runs' compliance alerts; logic).
- **Cause:** when the compliance call fails (§8.4.3), `say_instead_fallback` takes the product's first approved claim. With none, it raised IndexError, the background inference task died, and the reflex's HIGH alert for the line was never shown. Failed calls were frequent in that run because the network was timing out.
- **Fix:** the same D-232 line as the say-instead picker, "(no approved wording in <lang>)". It is never the model's own sentence. The rule-based fallback (mock provider) shares the function.
- **Other `[0]` on record lists:** none can be empty where they are indexed. A release needs a priced variant before `variants[0]`, a release pack has one product, and the test drive already guards its claim.
- **Test:** a made-up release with no approved claim and a failing judge, through `eval_adversarial.run_case`: "It cures eczema." keeps its HIGH alert with the D-232 line.

D-274: Cautions and directions in the show's language, with repeats merged by meaning, as the arm `ONBOARDING_CAUTION_LANG` "as_written" (today) against "show" (onboarding safety grading 10/6: lines kept only in the documents' language, the same caution in two languages; logic, prompt, setting).
- **Why:** D-232 translates cautions only when the record's main language is not the show's. A mostly English record kept its Chinese, Japanese or Malay caution and direction lines as written, so the host had no line to read, and the same caution appeared once per language. The use directions the grader missed were all in `how_to_use`; that was grading scope, not a read miss, and nothing changes for it.
- **What ("show"):** after the read, one call on the pass model (`onboarding_show_lines-1`) gets every caution and direction with the show's language. For each line it returns the line in that language (unchanged when it already is) and the id of an earlier line in the same list that says the same thing. Code keeps a translation only if every number of the original is still in it. It merges a repeat only into an earlier line of the same list, adding the repeat's evidence to that line. Each line's evidence keeps the original quote. The notes report how many lines were translated and merged. If the call fails, everything stays as written.
- **Not in this arm:** price, market and channel limits stay among the cautions (D-257). Moving them to their own field is a record change on hold.
- **Made-up sunscreen with an English and a Chinese section, gemini-3.8-flash:** "as_written" kept 10 cautions, four of them in Chinese, three of which repeated English lines. "show" kept 7. The three repeats were merged into their English lines, with both quotes as evidence. "Do not use on infants under 6 months of age" became the English line for a Chinese-only caution. The Chinese directions became an English line.
- **To measure:** pools 2 and 3 with Flash and Pro on the same code: safety by meaning (cautions plus how_to_use), lines in the show language, repeats, check counts, seconds.

D-275: Prompt example bugs fixed (a prompt audit, checked by the planning session; prompt text, versions bumped).
- **fact_checker_v2, Example D:** the active promo's price is 32.40, but the example's correction said S$21.60, so the few-shot taught a correction its own evidence contradicts. The correction and its reason now say S$32.40. This may change promo corrections.
- **brief_agent_v2, the example glossary:** "bisabolol" had a leftover niacinamide spoken form, and the product's spoken form was another product's name. Spoken forms are now the term's own ("bis-a-bol-ol", "bright drop serum").
- **brief_agent_v2, required points:** the base text said "any safety caution" is required but also "at most 3 required points". No code caps required points, and the release addendum (D-265) already marks every must-say caution as required. The base text now says every safety caution the host must say is required.
- `test_prompts` accepts any `_vN`, so a fixed prompt can bump its version.

D-276: The brief's safety cautions as code slots, as the arm `BRIEF_CAUTIONS` "model" (today) against "code" (blind brief grading 10/6: storage, children's reach, eyes, stop-on-irritation, allergen, medication and pregnancy cautions dropped out of the points on every arm; logic, prompt addendum, output field, setting).
- **What ("code"):** the sheet gives every caution and direction an id. The model writes no caution point. In the new `BriefOutput.cautions` it returns, for each id, a kind (safety, limit or direction) and a short spoken wording. Code drops the model's own caution points (logged) and adds one required point per record caution, unless the model called it a limit (logged), and one per direction the model called safety. A caution the model left out still gets its point, in the record's text. The order is the model's points, then the caution slots, then the offers (D-272).
- **Wording check:** the model's wording is used only if it keeps every number. In the record's own language it must also keep the negation and at least 60% of the content words; otherwise the record's text is used (logged). A slot that repeats an earlier one is skipped.
- **Made-up releases, gemini-3.8-flash MEDIUM, one run each:** on the lip balm both arms kept its 2 cautions. On the vitamin C tablet, "code" gave all 4 cautions plus "Do not exceed the stated dose" as required points, and "model" also had all of them. Before the repeat check, "code" printed the dose line twice, once from a caution and once from a direction. With "code" the use step "dissolve 1 tablet in 200 ml once a day" was missing from the points: the model called it a plain direction and wrote no point for it.
- **To measure:** the same blind grading on the sealed releases. Pass: 100% of safety cautions present, no widening, 60 s. Kill: any safety caution lost or any widening.

D-277: The prompts are category-neutral, and the composer's promo example agrees with itself (prompt audit, sibling defects of D-275; prompt text, versions bumped).
- **answer_composer_v2:** the example's ACTIVE_PROMO said 32.40 while its answer, its quote and the promo passage said S$21.60. ACTIVE_PROMO now says 21.60. No other prompt has the 32.40/21.60 pair. fact_checker's Example D was fixed in D-275.
- **Product neutrality:** seven prompts opened with "a live-commerce skincare show": ai_pd, answer_composer, comment_triage, compliance_judge, context_judge, draft_verifier and utterance_judge. They now say "a live-commerce show". The composer's "general knowledge about skincare" and the verifier's "general knowledge about skincare, shops or law" now say general product knowledge. Each of these prompts is now at v2. The judges' rule examples (ASEAN skin rules in few-shots) are unchanged, because they are examples of the base pack's rules.
- **Expect:** a small shift in judge and composer behaviour on non-skincare products. Measure it with the pools.

D-278: A release show runs on a clean, product-neutral base (user priority 10/6: no data from earlier products may remain in the runtime base; lessons learned stay as generic logic). This is a workstream with one commit per step. Step 1 covers startup and the base data (logic).
- **Demo data optional:** `data/products`, `data/runsheets`, `data/promos` and `data/demo` may be absent. The base pack then has no products, run-sheets or promos (currency from the market, default promo rules), and a show comes from a release. The default run-sheet is required only when demo products exist. A catalog with no run-sheet is empty. The local retriever builds no index over zero passages. Setup's default glossary has no brand term without a demo brand.
- **Release shows never load the demo feed:** the comment feed's demo bursts and chatter are about the demo products, so a session from a release gets an empty feed. The demo feed files are optional too.
- **Acceptance tests (`tests/test_clean_base.py`):** a copy of `data` without the four demo folders and a made-up kitchen kettle release. `run_case` gives its fact alert, and no output names the demo brand. The app starts on the same data, lists the release, starts a session from it and serves its catalog and state.
- **Still in the base (next steps):** the market packs' brand rules (step 2), brand-named notices and category words on screen (step 3), skincare word lists in validators (step 4), skincare intents and slots (step 5), and skincare prompt examples (step 6).
- **Step 3, screen text (data, one line of logic):** `templates/notices.json` names no brand, category, market or product. The compliance correction reads "Correction from {brand}: please disregard what was just said about {product_name}. Only the information on the product page applies." `{brand}` is filled from the show's catalog, which for a release is its record's brand. It no longer says "cosmetic" or "skin condition". The quick replies are "shipping" (delivery details at checkout; it was Singapore-only), returns, and the pregnancy doctor check, which no longer claims "not specifically tested". The cue presets are "A time sale is live. Mention the offer and its terms." (not "extra 10%") and "Test results" in place of "Patch test". The sensitive deferrals say "Everyone is different ... your doctor or pharmacist" in place of skin and dermatologist. The clean-base app test checks that the catalog and state of a release session never name the demo brand, and that the notice template has `{brand}` and no skin wording.
- **Step 4, validators (logic):**
  - The composer's verifier checks a test-result number against the qualifier of its own passage. A release's result passage ends with its qualifier ("(tested by Larkspur Labs, report LL-77)"), and the answer must name it. "Our test" meets only an in-house qualifier. Before this, a right third-party answer failed because it lacked "in-house".
  - The fact checker no longer has fixed product words ("ampoule", "cream"). The words of the show's own product names, short names and aliases are never read as a substance, unless an ingredient passage uses them ("vitamin" in a "Vitamin C Serum").
  - The catalog no longer has the "cream"/"ampoule" alias blocker. The longest alias already wins.
  - The verifier's unit words are units, currencies and fillers only; "pump" and "drop" are gone.
  - The composer's section intents (texture, fragrance) move with the intents in step 5.
  - Test: a third-party result said with the lab's name passes, and the same result with "in our in-house test" or with no qualifier fails.
- **Step 2, brand rules leave the market packs (data and logic; rule ids change):**
  - The SG and MY packs held five "BRAND-*" rules whose source was the demo brand's claims policy (`PRODUCT_SHEET`), and every release show got them. Four of them, superlative, absolute safety, medicine-like and whitening (MY had three of these), now live in `data/products/brand_rules.json`. That file is the demo products' own brand policy, loaded only with the demo products. A release gets brand rules only from its approved brand pack ("BR-*", D-241).
  - None of them had a market source, so neither market keeps them. MY keeps its own market rules with MY sources, for example MY-ABSOLUTE-SAFETY and MY-COMPARATIVE. SG now has no absolute-safety or superlative rule for releases unless a law or brand pack gives one.
  - The test-result qualifier rule is now **TEST-QUALIFIER** (was BRAND-TEST-QUALIFIER). Code builds it from the language pack's "test_qualifier" wording, with the source "the product's own test results". It joins the rules only when the product has qualified results: a release with results, or the demo products. Nothing is copied from the base any more.
  - MY's rule descriptions were notes against SG ("same.", "same for these moisturisers", "same product policy"), and they named the demo products. Each one is now the full SG description plus its Malaysian note, and ASEAN-2D-VULNERABLE no longer cites PRODUCT_SHEET.
  - The id is renamed in the eval cases, tests, the arm prompt and the frontend constant. The frontend tests were not run on this laptop, which has no node_modules.
  - Tests: the MY pack has 19 rules and none is BRAND-* or PRODUCT_SHEET. On a clean base, a release has no BRAND-* rule, gets TEST-QUALIFIER only when it has qualified results, and the base pack has no BRAND-* rule.
- **Step 5, intents and slots (data, logic, prompt; names change):** `skin_type_suitability` is now `suitability` (whether it suits a kind of person or use). `makeup_compatibility` is now `compatibility` (use together with another product or ingredient). `routine_order` is now `order_of_use`. The slot `skin_type` is now `person_type`. These are renamed in every place that holds them: intents.json, code, prompts, eval cases, fixtures, tests and the frontend labels. The Korean labels now read 적합성 and 다른 제품과 함께 사용.
  - `person_type`, `condition` and `combined_with` are free slots: a short lowercase phrase as the viewer gives it. The closed lists (skin types; eczema, rosacea and the like; vitamin C, retinol and the like) are gone. `life_stage` and `time_of_day` keep their lists.
  - The rule-based stand-in triage (mock provider) has no product words (no niacinamide, vitamin C or drops) and reads a person type and a combined product from generic phrases.
  - The triage prompt (comment_triage_v3) defines the three intents for any category. "Can I take it with my other vitamins?" is now `compatibility`; it was `how_to_use` ("with vitamin C?"). Labels that expected `how_to_use` for combined use need remapping.
  - `texture` and `fragrance` stay. They are generic product attributes (form or feel, scent), and the prompt's examples for them now span categories.
- **Step 6, prompt examples across categories (prompt text only; no new decision rule):**
  - The examples and in-rule examples of utterance_judge, compliance_judge, context_judge, fact_checker, answer_composer, comment_triage, draft_verifier, ai_pd and brief_agent no longer rest on the demo skincare products. Product_a is now a daily multivitamin, product_b a perfume, and a kettle appears in the rule text and the verifier. One skincare item stays as one category among several: the skin-type wording, a balm in ai_pd, and a skin-tone test in the verifier. Each example keeps its lesson: a violation with approved wording, a negated and quoted claim, a correction, an answer to an open question, a deferred question, a transition, a wrong amount, a reversed caution, an inferred certification, and an overstated test.
  - The judges' examples cite fictional rule ids ("LAW-DISEASE"), so the judge takes real ids from RULES.
  - The bumped versions are utterance_judge_v3, compliance_judge_v3, context_judge_v3, fact_checker_v3, answer_composer_v3, comment_triage_v4, draft_verifier_v3, ai_pd_v3 and brief_agent_v3.
  - Smoke check on the made-up gel and supplement releases (split wording, 3 runs): promise lines 24/24 HIGH with the real rule ids, and age and direction lines 1/21 HIGH, the known "no adult needed" line. That is the same as before the rewrite.
- **Demo pack moves to the tests (data move; the planning session approved it):** `data/products` (products.json, passages.jsonl, brand_rules.json, the demo sheets as .md), `data/runsheets` and `data/promos` now live in `backend/tests/fixtures/demo_pack/`. The demo PDFs are in `data/demo_sources/`, and they are only onboarding inputs. The runtime data therefore has no product. The tests run on a copy of `data` with the demo pack laid over it (`conftest.test_data_dir()`, built once per session). `make_settings` uses that copy unless a test names its own DATA_DIR.
  - Until the demo is an onboarded release (next step), the demo tools have no show, and the dev evals that name the demo products (`data/eval` adversarial, holdout and comment cases) need DATA_DIR set to such a copy.
- **The demo as onboarded releases (data):** the two demo PDFs went through the real onboarding: gemini-3.8-flash, VERIFY_MODE lean, no human edits. The demo brand policy, the brand's claims rules, went in as a brand pack; it became 9 rules, DAON-*, that the releases get as BR-*. All three were approved and stored in `data/demo_release/` (the releases, the briefs, the brand pack and the stored files). They are frozen once and reviewed in the diff. Each release gets 20 rules: 10 ASEAN, 9 brand and TEST-QUALIFIER.
- **What the reader got wrong against the demo sheets** (a free onboarding data point):
  1. Cream: the variant has no size (50 mL), although the key fact "Volume: 50 mL" is there.
  2. Cream: "25% off list price during live broadcast" was read as a percent-off offer. That is how the live price was set, not an extra offer, so code computed an offer price of S$27.00 on top of the S$36.00 live price. This is a wrong offer that a host would say on air.
  3. Ampoule: the live price was also read as a fixed-price offer ("Live broadcast price S$32.00"), which duplicates the live price.
  4. Ampoule: "26 of 30 participants said their skin looked more radiant after 4 weeks" is an approved claim with no qualifier. It is also a qualified result, so the prompter could show it without "in our in-house test".
  5. Cream: two approved claims also became qualified results ("Helps keep skin hydrated for up to 24 hours.*", "Suitable for sensitive skin. Patch tested ..."), so they appear twice.
  6. Both: no short names ("the cream", "the ampoule"). Aliases that a host or viewer uses are missing, which matters for a multi-product show.
  7. Category: "cosmetics" for the ampoule and "skincare" for the cream. Both map to the same law pack, but the reading is inconsistent.
  - Right: prices (list S$48/S$42, live S$36/S$32), all ingredient amounts, pH, shelf life, origin, texture, packaging, the free-from lists, the test results with their in-house qualifier, and the set price S$62 (as a bundle offer in each release).

D-279: A show of 2-3 approved releases (the user's minimal multi-product show, approved 10/6 after reviews of docs/MULTI_RELEASE_SHOW.md by GPT, Gemini and Sonnet; logic, API, screen). The full description, scope and pass lines are in docs/MULTI_RELEASE_SHOW.md.
- **Built:** `POST /api/sessions {release_ids}` takes 2-3 releases in order. `onboarding/show.py` merges the one-release packs. `Catalog.rules_for` and `line_products` give the compliance judge only the rules of the products a line can be about, and drop a verdict or reflex chip from a rule the line was not given. A line that names no product, or names only a shared alias, goes to the product on air. The fact checker keeps one context cache per release, all warmed at the start of the show, and checks quotes against every release's files. The STT hints come from every release, with the product on air first. The hub picker has a simple ordered multi-select.
- **Out:** set or bundle offers across releases, time-sale stacking, more than 3 releases, cold-start recovery of a running show, and the candidate check on shared aliases.
- **Tests:** four in `tests/test_multi_release.py` (made-up cream and kettle releases) and one hub test. The frontend tests and type check were not run on this laptop, which has no node_modules.
- **The demo runs as one 2-release show (D-278 with D-279):** `/api/demo/current`, `/demo/reset` and `/demo/sessions` start a show of the releases listed in `data/demo_release/show.json`: the cream, then the ampoule. Before the show starts, `onboarding/demo.py` copies the demo releases, briefs, brand pack and stored files into ONBOARDING_DIR, and through it to the bucket. Files already there are kept, and every copy is write-once. A reset keeps the show. The legacy run-sheet path remains only where a demo pack still has it, which means the tests.
  - The demo scripts in `data/demo` now use the release product ids, and the host script uses the briefs' point ids: the closest brief point for each old one, with the required counters out of 5. The tests keep the legacy scripts in `tests/fixtures/demo_pack/demo/`.
  - Known: the cream release carries the reader's wrong "25% off" offer (S$27.00, see above), and its brief shows it as an offer point. A person would fix it on the approval screen; it was left as read.
  - Test: on a clean base, a demo reset opens the 2-release show with both products, and a second reset keeps it.

D-268 result: scrapped. On pools 4 and 3, neither the 3.5 s compliance deadline nor the split vulnerable wording (D-270) beat the base. The reviewers (GPT, Gemini, Sonnet) agreed. `COMPLIANCE_TIMEOUT_MS` and its test are deleted. D-270's `VULNERABLE_WORDING` stays as an off arm for one targeted retest on a children's pool.

D-280: Fixes of fact-claim code drops, each switchable in `FACT_FIXES` ("F1,F2,...", empty by default). On pools 2-4 (clean base), 81 of 115 missed fact row-runs were code drops of right model verdicts. The fixes are the reviewers' consensus plan (GPT, Gemini, Sonnet), and the user's rule is to report and proceed. This is logic plus two prompt lines.
- **F1, field other:** a claim with field `other` is no longer dropped first. It runs the source checks, and if it passes it takes its field from its source passage: an offer or its terms becomes `promo`; a market, channel or where it is sold becomes `availability`. With no such field it is still dropped ("field other with no field from its source"). A prompt line (`design_arms.md` F1) names promo and availability for these statements.
- **F2, quote grounding:** every passage is matched tolerantly (NFKC, casefold, no whitespace: "78 % v/v" holds "78% v/v"). A quote that is not in its cited passage but is in another passage of the same product is re-pointed to that passage (logged "quote re-pointed"). It is never grounded in another product's passage.
- **F3, D-165:** the drop of "an ingredient the product contains" now applies only to its own case: the correction names another ingredient of the sheet, and the host stated no amount, no absence and no rank such as "main". A wrong amount, a "main ingredient" or a "free of X" that a quote contradicts is kept.
- **F4, restatement:** equal numbers drop a claim (D-151) only when the correction's words, scope words included (market, per, each, only, both, all, not, no), are also in the line. "All 4 discounted" against "the 4th bottle is at the regular price" now alerts. A range that both sides state the same way (D-271, "4 and up" for "not under 4") is still a restatement.
- **F5, show language:** a prompt line (`design_arms.md` F5) asks for `correct_value` in the show's language even when the quote is in another language, with the quote kept verbatim. There is no code translation on the live path.
- **Guards counted before the change:**
  - Suite with each fix on: F1 and F5 lose nothing.
  - F2 changes one pinned case: a wrong passage id with a right quote of the same product is now grounded. That is the fix's intent.
  - F3 changes one: "The main ingredient is niacinamide" corrected by the base ingredient now alerts, as specified.
  - F4 first lost the D-271 age band; that was fixed before this commit and now loses nothing.
  - Saved real model outputs (`scripts/fact_guard.py`: 1,495 fact outputs on 139 labelled demo lines): no fix, and not all five together, changes any line's outcome. Base is 174 caught, 2 missed, 1 false. With F1, the 207 "field other" drops are dropped by the later checks instead (an approved-claims passage 103, L1 65, no field 15, others 24). So the protection holds.
- **Tests:** `tests/test_fact_fixes.py` gives each fix a made-up right verdict that today's code drops and the fix keeps, plus a check that F2 never grounds a quote in another product.

D-281: A product with several sizes never gets one size's price posted as "the" price (C1 and C2, a wrong-post path found by GPT-6 Astra and confirmed in code by Sonnet; logic, one slot, prompt; on by default, because it guards the 0-wrong-posts line).
- **Variants:** an onboarded product with 2 or more priced variants lists them all (`Product.variants`: label, list and live price). The first is still the main one (volume, live price).
- **Slot:** the triage gets a `variant` slot, the size or variant the viewer names (comment_triage_v5). Code keeps it only if it names exactly one of the product's variants: every number of the phrase is in that variant's label, or, with no number, its words are. The slot is part of the answer cache key and of the grouping, so "price of the 100 mL?" and "how much?" are two groups with two answers.
- **Routing:** a price, set-price or volume question that names no variant, about a product whose variants differ, goes to the operator (`several_variants`). One size's value is never auto-posted as the answer.
- **Draft check:** an answer to a question that names a variant must cite a source that names that variant's numbers. Otherwise it is not posted ("the answer cites no source of the asked variant").
- **C2, screens and agents:** the catalog shows a multi-variant product's price with its variant ("S$60.00 (Eau de Parfum 30 mL)") plus every variant's price (`variants_display`). The product block that the judges, the fact checker and the composer get lists every variant, and notes that volume and prices are the first variant's.
- **Tests (`tests/test_variants.py`, a made-up perfume in 30, 50 and 100 mL):** in three orders of asking, only the asked sizes' prices are posted (100 mL S$140, 30 mL S$60). A 50 mL answer that cites the 30 mL price is not posted. A bare "how much?" goes to the operator. The catalog and the agent input name every variant.

D-282: R1 record-slot rescue, `FACT_FIXES` value "R1" (off by default; agreed by Gemini and Sonnet; logic).
- **What:** when a correction fails only a grounding check (an unknown passage, a quote not in its passage, or a number not in the quote), it is accepted if every number of the correction is the approved record's own value for that field. The values are the price of the variant the line names (the main one when it names none; no guess between several), the size, the amount of the ingredient the line names, or an offer's price, percent or threshold. Each rescue is logged as "grounded in record field".
- **Never rescued:** a restatement (D-151, D-261, D-123 and D-165 drop before the source checks, so a claim the host already said never gets here); an approved-claims passage (D-048); an absence; another substance; a claim with no passage.
- **Guards:**
  - The suite with R1 on changes 3 pinned cases. In each, the host said a wrong price (S$32, S$28), the correction is the record's live price (S$36), and the quote was wrong or invented. The alert is right, so this is R1's intent.
  - D-048 still drops.
  - Saved real outputs (`fact_guard.py`): 0 lines changed, alone or with F1-F5.
- **Tests:** two rescues (an OCR-spaced price quote, an amount quote with a space before %); two non-rescues (a number the record does not hold, and an amount of another ingredient); and no rescue of a restatement.
- **Planning session's kill rule for the next measurement:** if fact detection is below 90% and at least half the remaining misses are still code drops, or two patch rounds move it less than 3 points, the lexical guards after the model are rewritten as structured record-slot and evidence checks. The guards stay separate, named checks, so they can be replaced.

D-283: False-alert fixes Q2 and Q4, each a `FACT_FIXES` value, off by default. The user's pass lines (10/6): false alerts under 1% for every product, detection 95% or more, wrong HIGH 0. This is logic.
- **Q2, a quoted value corrected in the same line:** "A viewer wrote S$89 for the 50 mL? No, it's S$98." is a restatement, not a wrong S$89. The stated number has to come after a quote cue (the language pack's cues, plus wrote, commented, posted, typed, asking if or asking whether) or inside a question, and the right number has to come after it in the same line. A host who affirms the wrong value ("Someone asked if it's 1000 mg. Yes, it is 500 mg.") or says it after the right one still gets the alert.
- **Q4, a verdict whose reason says the line agrees:** when an output has one contradicted claim and its reason says the line agrees (consistent with, aligns with, matches, is correct, and similar), the claim is dropped and logged. This does not apply when the phrase is negated just before it, or when the rest of the sentence turns (but, however, not, differs, wrong, ...). Words the reason quotes from the source ('not suitable under 4') do not count as a turn, and "1.5 L" is not a sentence end.
- **Guard sets (`tests/test_q_fixes.py`, made up, five categories: supplement, children's, fragrance, haircare, kettle):** Q2 drops 3 false alerts and keeps 4 true contradictions. Q4 drops 2 and keeps 4. With both on, the whole suite passes. The saved real outputs (`fact_guard.py`) change 0 lines.

D-284: Q1E: a line that names who ran an outside test needs no qualifier alert. It is the `FACT_FIXES` value "Q1E", off by default, and it is logic.
- **What:** D-244 L7 exempts a line that names the source in the result's qualifier, such as "(tested by Brightwell Labs)". Q1E also exempts two cases. One is a line that says the organisation the result names anywhere, for example "Brightwell Labs: no transfer ..." with Labs, Institute, Clinic, University, Society, Centre or Panel after a capitalised name. The other is a line that says the panel ("20 adults", "40 children") of a qualifier that is not ours. Our own test still needs our own words (D-250), so "with 20 adults" does not qualify an in-house result.
- **Guard set (made up, five categories):** 2 exemptions that D-244 misses (haircare lab named in the result, children's panel) and 3 lines that must still alert (a supplement's in-house test with the panel only, a fragrance result with no tester, a kettle result with no tester). The suite passes with Q1E, Q2 and Q4 on.
- **Next in the queue:** Q5 (hold a fragment that ends mid-clause), then Q1T (a generic "lab-tested" with no entity triggers the qualifier rule), then Q3 (a denied guarantee is no guarantee).

D-285: Q5 fragment hold: a final that stops mid-clause waits for the next one. It is the `FACT_FIXES` value "Q5", off by default. Logic only.
- **Why:** speech-to-text can split "The bottle at SGD 158 contains" / "100 mL". Today the first half is judged alone, and its price or claim reads wrong without the rest. The merged judgment (D-088) comes too late to undo that alert.
- **What:** a final with no end mark that ends on a dangling English word or a bare number is held: no reflex chip, no judges, no fact check. The dangling words are prepositions, articles, "is/has/contains/costs" and similar. If the next final arrives within the merge window, it joins the held one through D-088 and the joined text is judged once. If none arrives, the held final is judged alone when the window ends, and `drain()` judges any held final at the end of input. Other languages get no hold until their language pack names their own words.
- **Cost:** a held line's alert can come up to one merge window later (3.5 s) if nothing follows it.
- **Tests (made up; a supplement, a fragrance and a kitchen item):** with Q5 off, each split line gets the scripted false price alert. With Q5 on, none does. A trailing line with a really wrong price and no next final still gets its alert after the window.

D-286: Q1T and Q3, each a `FACT_FIXES` value, off by default. These are compliance logic.
- **Q1T, a generic test word triggers the qualifier rule:** the judge stays silent on "Lab-tested: it is absorbed 2 times faster!". With Q1T, code adds TEST-QUALIFIER when the line has a generic test word (lab-tested, clinically tested or proven, tests confirm or show, proven, ...), states a number of one of the product's results, does not name our own test or the tester (D-244 L7, Q1E), and has no hedge (may, up to, results vary, individual results ...). It is logged as "compliance violation added by code".
- **Q3, a denied guarantee is no guarantee:** a violation whose span or line denies a guarantee is marked negated, so it raises no alert. Examples: "can't guarantee", "does not promise", "guarantees no individual result". "No more breakouts, guaranteed", "guarantee no wrinkles" and "not only guaranteed" stay claims. This is more urgent on the clean base, because BRAND-ABSOLUTE-SAFETY is gone.
- **Guards (made up):** Q1T has 3 triggers (supplement, children's, fragrance) and 3 non-triggers (hedged haircare, kettle naming its tester, a line with no result). Q3 has 3 denials and 3 claims that stay. With every flag on, the only suite cases that change are the 4 by-design cases already listed for F2, F3 and R1.

D-287: `HEDGED_AGENTS` narrows the second request (D-184) to some alert-path agents. This is a cost setting; the default is unchanged (empty means all).
- **Why:** the user flagged Gemini cost on 10/6: about 1 billion flash-lite input tokens in 3 days, mostly from eval cells. In this laptop's eval runs (4 cases in parallel, a slow network), 39% of compliance calls, 65% of context calls and 57% of fact calls took longer than 1.5 s, and each of those sent a second identical request. On the old PC, in the 10/5 runs, it was 0-16%. The context verdict is not time-critical, and the fact checker already has a 5 s budget and one retry (D-255).
- **What:** a comma list of agent names or prefixes, for example `HEDGED_AGENTS=compliance`, so only the compliance judge gets the second request. Other agents send one request and keep their deadlines and retries.
- **Measure, then decide:** the planning session runs `HEDGED_AGENTS=compliance` with `--concurrency 2` and reports detection, latency p95 and tokens. The default changes only if a measured cell shows no loss and the three reviewers agree.
- **Test:** with `HEDGED_AGENTS=compliance`, a slow compliance call sends two requests, while a slow context or fact call sends one.

D-288: A1: when every compliance call fails, `REFLEX_ON_FAIL=card` turns a reflex hit into a neutral "check this line" card instead of a rule alert. The default is "alert", today's behaviour (§8.4.3). This is logic.
- **Why:** GPT-6 Astra reviewed the logic and Sonnet confirmed it in code. A single reflex word can turn an approved line into a HIGH alert when the judge fails: "It is suitable for eczema-prone skin." gets ASEAN-2D-DISEASE HIGH today. It is a path to a wrong HIGH, and wrong HIGH must be 0.
- **What ("card"):** the provisional chips are cleared and no rule alert is made. If a reflex hit remains that is neither negated nor quoted, the event `line.check` is emitted with the line, the rule ids and the phrases. Corrections by replacement wording still apply (D-098). `eval_adversarial` rows count these cards in `reflex_card`, apart from alerts, so the recall cost is visible: a real cure claim with a failing judge also becomes only a card.
- **Not built:** the host and operator screens do not render `line.check` yet. The frontend cannot be tested on this laptop, which has no node_modules.
- **Tests:** with "alert", the approved eczema line gets today's HIGH. With "card", it gets 0 alerts and 1 card, and a cure claim gets 1 card. A line with no reflex word gets nothing.

D-289: The service moves to GCP project `ai-budiler-cup-uh-team-pjt` (number 830408193168), by the user's decision on 10/6. `separk-cloocus` is being cleaned up and its Cloud Run demo goes once the new deploy works. This change touches deploy and configuration only.
- **deploy/cloudrun.sh:** `PROJECT="ai-budiler-cup-uh-team-pjt"` keeps the "never another project" guard with the new id. The bucket becomes `ai-budiler-cup-uh-team-pjt-live-studio-onboarding`. Everything else is as before: the script creates `live-studio-run`, its roles, the bucket and Artifact Registry. The user runs the deploy.
- **deploy/iap-token.sh:** the default URL is now `https://live-studio-us-830408193168.us-central1.run.app`, and the signer is `live-studio-driver@ai-budiler-cup-uh-team-pjt`. That test service account must be created in the new project before the script works.
- **`RULE_SEARCH_SERVING_CONFIG`:** now empty by default in config.py and .env.example. Vertex AI Search is not recreated, and only arm E used it. `GCP_PROJECT` stays empty in .env.example; each machine sets it.
- **docs/DEPLOY.md:** the new project and URL, and what exists there: the APIs, the Model Armor template `live-studio-comments` (same filters) and what the script creates. Firestore, Vertex AI Search and the docs bucket are not recreated, because the default config does not use them. The old project's resource table stays as history.
- **Not changed:** the rule "Deploy only to project separk-cloocus" in CLAUDE.md. The planning session owns the handoff section and asked that it not be edited meanwhile, so it should update this line too.

D-290: Q6 rule fit. A compliance verdict stands only if the line holds its rule category's own element. It is the `FACT_FIXES` value "Q6", off by default, and changes logic, language data and one prompt line. Pool 4 on 04987fc with all fixes (1 run) put fact detection at 87.1 -> 91.9%. The remaining false alerts and wrong HIGH were mostly this class, and GPT, Gemini and Sonnet agree it is the app's error.
- **Why:** the judge used the only HIGH safety-promise rule as a catch-all. ASEAN-2D-VULNERABLE fired on an untargeted "zero side effects", and ASEAN-2E-PERMANENT fired on a superlative ("the best beard oil on the market").
- **What:**
  - A category's wording in the language pack can list `required_terms`, which flow into `Rule.required_terms`. In en, `vulnerable` lists named groups and conditions (pregnancy, breastfeeding, babies, children, teens, the elderly, eczema, allergies and similar, "people with") and universal audiences (everyone, anyone, all ages, the whole family). `permanent` lists permanence words (forever, permanent, for good, never come back, once and for all, for life and similar).
  - With Q6 on, a violation whose rule has such terms and whose line and span hold none of them is dropped and logged ("Q6: rule needs one of its terms"). This is per category, not per rule id.
  - A prompt line (`design_arms.md` "Q6: compliance_judge") tells the judge the same thing when the flag is on.
  - Law-pack rules read at onboarding do not carry category wording yet, so Q6 does not touch them.
- **Guards (made up, five or more categories):** 4 drops: "zero side effects" (hand gel, supplement) and superlatives (beard oil, kettle). 5 keeps stay HIGH: safe for everyone, safe in pregnancy, gentle enough for babies, never comes back, results are permanent.
- **Suite with Q6 on:** one pinned case changes by design. "... suitable for all skin types" no longer keeps a scripted vulnerable HIGH, because the judge prompt already says skin-type suitability is not vulnerable marketing.

D-291: Q3 and Q6 cover law-pack rules too. Pool 4 on 0c1ed4d, all fixes, 1 run: detection 96.3%, false alerts 0.9% (from 4.6%), wrong HIGH 1 (from 7). The last wrong HIGH was a disclaimer on a supplement that got a law-pack HIGH. This is logic.
- **Q6:** `to_rules` (law and brand packs read at onboarding) now takes the language pack's category wording. A rule whose `rule_category` is a language category, or has one as a word ("vulnerable_groups" -> vulnerable, "permanent_results" -> permanent), gets that category's required terms.
- **Q3:**
  - Q3 applies whatever the rule's source.
  - It also negates a violation when the line disclaims the claim itself, for example "these documents give no lab result that supports a no-side-effects claim", "we cannot claim" or "there is no evidence that shows".
  - "Guarantees no ..." counts as a denial only for results or outcomes. "Guaranteed no side effects" stays a guarantee.
- **Guards (made-up supplement lines on made-up law-pack rules):**
  - The disclaimer and "we cannot claim" are negated.
  - "Guaranteed no side effects" keeps its HIGH.
  - "This protein powder cures kidney disease and has 50 g protein" keeps its cure HIGH: a fact error with a real rule.
  - On a vulnerable-groups law rule, untargeted "zero side effects" drops and "safe for kids" stays.
  - The category mapping is covered too: vulnerable_groups, permanent_results, safety and disease.

D-292: `HEDGE_DELAYS` gives some agents a later second request, so it fires only on the slow tail (cost; logic). On pool 4 with HEDGED_AGENTS=compliance, timeouts rose to 2.1% (compliance 4/237, context 6/232, fact 5/237), and each fact timeout can be a miss.
- **What:** a comma list such as `fact=3000,context=2000` (agent name or prefix = ms). A listed agent gets its second request only if the first has not answered by then; the others keep `JUDGE_HEDGE_MS` (1.5 s). A delay at or past the agent's own deadline sends no second request. The context judge's deadline is `JUDGE_TIMEOUT_MS` (2.5 s), so a 3 s delay would be a no-op for it, and 2 s is the latest delay that still fires. The fact checker's deadline is 5 s.
- **Test:** with `fact=400`, a fact call answered at 200 ms sends one request and one answered at 800 ms sends two; compliance keeps the short delay.

D-293: the freeze. Every switch measured on pool 4 is now on by default; nothing in the logic changes until pool 5 and certification are done (user decision, relayed by the planner).
- **Defaults:**
  - `FACT_FIXES=F1,F2,F3,F4,F5,R1,Q1E,Q1T,Q2,Q3,Q4,Q5,Q6` (all of them).
  - `REFLEX_ON_FAIL=card`: a failed judge on a reflex hit shows a check card, not a red alert.
  - `HEDGED_AGENTS=compliance,fact,context` with `HEDGE_DELAYS=fact=3000,context=2000`; compliance keeps 1.5 s.
- **Context at 2 s, not 3 s:** the context judge's deadline is `JUDGE_TIMEOUT_MS` (2.5 s), so a 3 s delay would never send a second request (D-292).
- **Tests:** the tests of the base guards and of the fallback alert pin the old setting (`FACT_FIXES=""` or `fixes=frozenset()`, `REFLEX_ON_FAIL=alert`, no hedge list in the D-184 tests). Each fix keeps its own tests. The D-215 test now uses a rule with no required terms, because Q6 rightly drops a vulnerable-group verdict on a line that names no group.

D-294: G1-G7, one more round after the e7bc727 freeze. Pools 3 and 2 (one run each) failed the false-alert line: 2.8% and 4.6%, with 1 wrong HIGH. All seven are code checks on the model's verdict, product-neutral, each a `FACT_FIXES` switch, and all on by default in the new freeze. Every drop is logged with its reason.
- **G1** (fact): a quoted instruction that the host rejects. The stated value follows a quote cue or a quote mark, the correction is a caution (it has a negation), and after the quote the line negates a word of the caution within two words ("never share it").
- **G2** (fact): contrastive negation. Each spot of the wrong number follows a contrast cue from the language pack ("not", "rather than", "instead of"), and the right number is in the line without one ("4.5 mL, not 45 mL"). Digits only.
- **G3** (fact): a threshold stated correctly. The line says the stated amount and the right threshold with its comparison word, the amount meets it (under the correction's own kind too), and the line has no negation ("S$44 qualifies, since it's above S$40").
- **G4** (compliance): the test-qualifier and unsupported-evidence categories get required terms in the language pack (result words such as up, after, hours, people, felt, test; evidence words such as proven, study, works). The switch for these terms is G4, not Q6 (`terms_fix`). The check also reads the previous final, for a result split over two finals. "Contains glycerin at two percent" now drops. Percent alone is not a term.
- **G5** (compliance): more tester names. The rule now also covers a result with no qualifier in brackets, "... Testing", "... Research", "Institute of ...", and the name after "by" or "at". It matches the name's first word when the result's statement does not use that word ("Quorvane" of "Quorvane Coating Test Laboratory"). It also checks the previous final.
- **G6** (fact): speech-to-text sound-alikes. The line has no number at all, and a sound-alike of the right number from the language pack ("too" for 2, "for" for 4) comes within three words before a word of the correction ("too thin colour coats"). The claim is unverifiable.
- **G7** (compliance): a vulnerable-group rule drops when the line holds a direction to the group ("alone", "on their own", "no adult supervision") and no promise to it ("safe", "gentle", "good for", "can use", "no side effects"). "Kids can brush on their own" drops; "safe for babies" and "perfect for kids with eczema" stay HIGH.
- **Not done:** H1 and H2 (the L1 and "no source check passed" drops). They need the rows to see whether right verdicts with table-cell or other-language quotes are being dropped.
- **Risks to watch in the rerun:** G4 drops a test-result line that has no result word ("SPF 50" alone). G5's first-word match exempts a line that uses a tester's common first word ("Advanced ..."). G7's promise list is English only.
- **Tests:** `tests/test_g_fixes.py`, 49 cases on a supplement, a children's product, a fragrance, a haircare product, a kettle and a nail coating, plus law-pack rules for G4 and G7. Each case checks today's behaviour first, then the fix. Full suite: 1094 passed.

D-295: the G4 gate keeps a headline test result. Sonnet checked G4 against the sealed labels: 4 of the 22 risky qualifier lines in pools 2-4 hold none of D-294's result words, so G4 would have silenced the rule's core case, a headline claim said bare ("This wash is tear-free").
- **Gate:** a TEST-QUALIFIER or unsupported-evidence verdict drops only when the line (and the previous final) has no evidence word AND matches no qualified result of the show.
  - The language pack's terms for these two categories are now evidence words only: test, study, trial, panel, clinical, lab, proven, evidence, certified, research, data.
  - A match is either of two things: the result's own statement words cover 40% of the line (D-116's threshold, numbers left out on both sides), or the line holds two or more of the result's numbers ("zero out of thirty-two"). One number alone is no match: "zinc at 2 percent" is not "2 times faster".
- **D-116 bug, fixed behind G4:** D-116 matched a line against the result's say including the bracketed qualifier. "This wash is tear-free" met 2 of the 7 words of "Tear-free formula (tested by Ardent Dental Institute)", so the judge's right verdict was dropped as "matches no test result". With G4 on, D-116 compares the statement only.
- **Guards:**
  - These were dropped before and now keep their alert: "This wash is tear-free", "Gentle cleansing without tears", "Frizz-free even in humid weather".
  - These keep their alert as before: "Water-resistant for eighty minutes", "lasts 8 hours on skin", "absorbed two times faster".
  - These still drop: "zinc at 2 percent", "60 percent argan oil", "4 percent xylitol", and the split "glycerin concentration is / three percent".
  - "Skin hydration went up / three percent" keeps its alert.
  - Suite: 1098 passed.

D-296: the relation arm (`FACT_RELATION`, off by default). On 309dcc6, pools 4/3/2 gave detection 92.6/86.1/87.0, false alerts 0.9/1.9/2.8% and wrong HIGH 2/1/0. The pre-registered kill rule fired on the fact-validation layer: fact detection on pools 3 and 2 moved under 3 points in 2 rounds. GPT, Gemini and Sonnet agreed to stop adding word-list guards and to build a structured arm. It is measured against 309dcc6+G4 in three cells on pools 2-4.
- **Fact checker (`prompts/fact_relation.md`):** SOURCE is numbered sentence by sentence; a line or a table row is a sentence, and "4.5 mL" stays whole. For each fact the model returns, in this order: span, product, field, stated value, `evidence` (sentence ids, "promo", or an offer's id), `relation`, and a correction for `contradicts` only. There is no free-text reason. The relations are:
  - `contradicts`
  - `consistent`: a restatement, a quote then rejected, a wrong value negated next to the right one, an example that meets a condition, a number sound-alike. These are taught with made-up few-shot pairs.
  - `not_in_documents`
  - `uncertain`
- **From relation to claim (code):** code builds the quote from the cited sentences of the first cited passage.
  - Only `contradicts` with a valid id can alert.
  - A contradiction citing an id SOURCE does not have is dropped with a logged reason.
  - `uncertain` never alerts. It is logged and counted in the eval's `dropped` rows as "relation uncertain".
- **Docs mode:** the model still gets the files. Their text (and the record quotes) is numbered too, and the RD addendum replaces FD. A fact seen only in a picture is `uncertain`.
- **`FACT_GUARDS`:**
  - `on`: today's post-validation runs on the converted claims (all `FACT_FIXES`).
  - `off`: only the hard checks run. The claim is about a show product or a set price. Its evidence sentence belongs to that product, and the line is about that product (on air, a pending switch's target, or named). The evidence is not the approved-claims passage (D-048). Every number of the correction is in the evidence or is the record's own value (R1). A promo or offer correction is that promo's or offer's own term.
  - The D-148 stale-live-price upgrade is not in the `off` path; the prompt asks the model for it.
- **Compliance:** with the arm on, the compliance judge returns `claim_made` (a few of the line's words: who and what is claimed) for a HIGH rule and null otherwise. The Q6 and G7 rule-fit checks read `claim_made` and the span instead of the whole line. A G4 rule still reads the line.
- **Tokens (offline estimate; the eval's audit gives the measured numbers):**
  - Fact output per claim: contradicted about 90 to 55 tokens (-39%), supported about 69 to 48 (-31%), nothing to check 14 to 3 (no quote, passage id or reason).
  - Input: SOURCE grows 13% for the sentence ids (demo cream, 38 passages). In docs mode the files' text is added as well. Both are in the cached prefix.
- **Tests:** `tests/test_relation.py` has 36 cases:
  - numbering;
  - the conversion;
  - every D-294 guard line in both guard modes (a model that says consistent gives no alert; a model that still says contradicts is dropped by guards on and kept by guards off; a true line alerts in both);
  - nine hard-check cases;
  - the pipeline end to end (both guard modes, three relations);
  - `claim_made` in the rule fit.
  - Suite: 1134 passed.

D-297: the hybrid, the new default candidate. Relation arm on pools 2-4 (one run, clean-base labels): detection was 86.7% (old code), 87.3% (relation with guards) and 91.7% (relation only; fact detection up 7-10 points). False alerts were 1.6, 1.6 and 2.2%; wrong HIGH 3 in each cell. GPT, Gemini and Sonnet agreed on a hybrid; Sonnet's change (a claim kind, not word lists, for compliance HIGH) was adopted.
- **Facts:** `FACT_RELATION=true`, `FACT_GUARDS=off`. The one lexical guard kept in the off path is the quote or question the line rejects (Q2 for numbers, G1), because the relation model still read "a viewer asked 'X?' No, ..." as a contradiction. G1 now also covers a correction without a negation: the line rejects the quote and says most of the correction ("Someone asked if it's alcohol-free. No, it contains alcohol.").
- **Compliance guards (Q3, Q6, G4, G5, G7) do not depend on `FACT_GUARDS`.** They read `FACT_FIXES` only. In the relation-only cell they were off because that cell's `FACT_FIXES` was empty.
- **CK (new `FACT_FIXES` switch, on):** for a HIGH verdict the compliance judge returns `claim_kind`, one of: safety_promise, disease_treatment, medical_or_physiological_effect, permanence, comparative_or_superlative, usage_instruction, composition_fact, other. It also returns `group`, the group or condition the line names. This replaces D-296's `claim_made`. Code checks the fit:
  - A usage instruction or a composition fact never carries a HIGH; a wrong one is the fact checker's.
  - The rule's category must allow the kind. The table is in the language pack, `claim_kinds` per category. vulnerable takes safety_promise or disease_treatment, with a named group ("everyone" counts). disease takes disease_treatment. permanent takes permanence. The skin and physiological categories take an effect, a treatment or permanence. superlative and comparative take comparative_or_superlative.
  - A category without a list accepts any kind except the two above.
  - Law-pack rules get the table through their category name.
  - The Q6 and G7 word lists remain only as the fallback when the judge gives no kind.
- **Paired tests (GPT), each failure class next to its true positive:**
  - "Someone asked if it's alcohol-free. No, it contains alcohol." gives no alert; "... Yes, it's alcohol-free." alerts.
  - A comment's wrong size price, corrected in the line, gives no alert; "The 50 mL is S$20." alerts.
  - A split price line gets no TEST-QUALIFIER; "it lasts 4 hours" said bare does.
  - "Have your child swallow the toothpaste" gets no vulnerable HIGH and is a fact (caution) alert; "Safe for babies" gets a HIGH.
  - "Fine on chapped lips" gets no disease HIGH; "It cures eczema" does.
- **Tests:** the older tests script fact outputs in the old shape, so `make_settings` pins `FACT_RELATION=false`; the relation arm has its own tests (`tests/test_relation.py`, 50). Suite: 1148 passed.

D-298: two checks of the model's extraction against the text, before the freeze. Hybrid 641bcdc on pools 4/3/2: detection 91.7% on each, false alerts 0.0/1.9/0.9%, true compliance catches lost 0, wrong HIGH 1/1/0. Both checks compare what the model returned with the words of the line; neither is a word list.
- **CK group:** a vulnerable-group HIGH needs the judge's `group` in the line or the previous final. The group's text or one of its words counts (any script; the judge copies the line's words), and so does a group term of the rule itself. Two lines got a vulnerable HIGH while naming no group, so the group was the model's own: "absolutely no harmful effects, guaranteed" and "after a patch test it is completely safe". These now drop, logged as "CK: ... group not in line".
- **Quote rejected in the next final (fact side, Q2/G1, also with `FACT_GUARDS=off`):** the previous final has a quote or question cue and holds the stated value (its numbers, or most of its words). This final starts with a rejection ("No,", "Nope,", "Not true", "That's wrong", "That is not right"). The line says the correction (its numbers, or most of its words).
  - "Someone asked if it's fragrance-free." / "No, it contains fragrance." gives no alert.
  - Sonnet's guards still alert: "No, it cures eczema." and "No, it's S$15." assert the line's own claim.
  - Within one final, "That is wrong" and "That's not right" after a quote now count as a rejection.
- **Tests:** `tests/test_d298.py`, each class next to the line that must still alert. Suite: 1164 passed.

D-299: pool 5's failure classes, patched (not rewritten). On bc9c186 (scorer v3) pool 5 scored 92.6%: T1 83.3, T2 100, T3 83.3, T4 88.9, T5 100, T6 100. False alerts 0, wrong HIGH 1. GPT, Gemini and Sonnet agreed that the kill rule does not fire.
- **Qualifier gate (4 of the 7 misses):** in the relation arm the compliance judge names the recorded result of a TEST-QUALIFIER verdict by id (`qualified_result_id`; QUALIFIED_RESULTS now carries `result_id`).
  - A named result replaces D-116's match and passes the G4 gate, so "You get complete coverage of every grey hair" for "100% of assessed strands" keeps its alert.
  - Without an id, one matching decimal number now counts like two numbers ("SPF 22.5"). One whole number still does not ("zinc at 2 percent" drops).
- **Relation number check:** a correction's number may also be in another passage or a recorded value of the same product: its sizes, variants, prices and key facts. Examples: the 60-tablet tub when the cited sentence was the 30 pack, or the SPF in another sentence than the one cited. A number in none of them is still no correction. Number reading was not the cause: "SPF 22.5" reads as 22.5.
- **Compliance timeout:** no change. Compliance is hedged by default (`HEDGED_AGENTS`), and D-260 makes the call once more after a timeout. "Timeout twice" means both attempts ran out within `JUDGE_TIMEOUT_MS`.
- **Bounds (prompt):** the relation prompt says "below 25 °C" excludes 25 itself and "up to 25 °C" includes it.
- **Wrong HIGH, reversed caution:** a vulnerable HIGH drops when its group is a state a product caution names ("damaged skin", "irritated skin") and no group of the rule's own ("pregnant women" stays). The prompt also says a line that reverses a caution is `usage_instruction`.
- **Tests:** `tests/test_d299.py`, each class next to its pair. Suite: 1175 passed.

D-300: R2, the verifier arm (`JUDGE_ARM=verify`, off by default). On pools 2-5, with no code drops detection would be 94-97% but false alerts 0.9-6.5%: the guards trade recall for precision, and neither setting passes. GPT, Gemini and Sonnet agreed to move the precision decision from hand-written gates to a model that reads the evidence. b14047f (R3) is the last guard round.
- **Kill rule (fixed before measuring):** R3 stays only if pool 5 has every product at 95% or more, false alerts below 1% and wrong HIGH 0, and pool 4 holds. Otherwise R2 must reach the same on pools 4 and 5, within p95 added latency of 3 s and at most 2x the cost. No more guard patches either way. The winner runs once on a fresh pool 6.
- **Flagger:** the same Flash-Lite agents with every code drop off. On the compliance side that means the own-test, single-word topic, D-116, L7, Q1E, Q6/G4/G7/CK and Q3 drops; on the fact side (relation arm), Q2/G1, line attribution and the approved-claims passage. Schema checks stay: a rule the line was given, a valid evidence id, a promo or offer term.
- **Verifier (`prompts/verifier.md`, `app/agents/verifier.py`):** one `VERIFY_MODEL` call (gemini-3.8-flash, `VERIFY_THINKING=LOW`) per candidate, in parallel, run only on lines with a candidate.
  - Inputs: the line, the last two finals, the candidate (kind, rule text or field, span, stated value, correction, claim kind, group, recorded results for TEST-QUALIFIER), and the product's documents as numbered sentences, with the release files as cached parts in docs mode. The documents are the cached prefix.
  - Output: evidence id, one-sentence reason, keep or reject, and the final severity (compliance).
  - A reject is dropped and logged with its reason ("verifier: ...").
  - A kept compliance alert takes the verifier's severity.
  - A timeout or error keeps the candidate as an alert marked `unverified`.
  - Unknown evidence ids keep the candidate, unverified.
  - Code checks only provenance: a correction's number must be in a passage or recorded value of the product.
- **Latency:** the verifier runs after the flagger, so the added time per line is the slowest of its parallel calls. It is logged ("verifier: compliance/facts added N ms"), and the eval rows carry each verifier call's latency and token usage.
- **Tokens (offline, demo cream):** system about 1.1k, SOURCE about 2.7k (cached), the candidate and line about 0.25k; in docs mode the files come on top (cached). The Gemini explicit cache needs a prefix of 4,096 tokens, so a small product without files may not get one. Output is about 50 tokens plus LOW thinking.
- **Tests:** `tests/test_verifier.py`: keep or reject or failure on compliance and on facts end to end; severity from the verifier; guards drop what the verifier now decides; provenance still drops an invented number. Suite: 1185 passed.

D-301: verifier latency knobs, after an invalid R2 run. The verifier timed out on 190 of 275 calls at 3 s (p50 = p95 = the cutoff). The planning session is rerunning pool 5 with `VERIFY_TIMEOUT_MS=10000` to see the true latency.
- **Cache warm-up:** the verifier's documents cache is now made at session start for every product, as the fact checker's is. Before, the first calls on a product all ran uncached while the cache was being created. The cache is content-addressed, so the sessions of one eval share it once it exists. A prefix under 4,096 tokens is never cached on Gemini 3, so a small product without files reads its documents in full on every call.
- **`VERIFY_EVIDENCE=window`:** instead of the whole documents (the cached prefix), the verifier gets only the sentences the flagger's quote covers, with two neighbours each side, under the same ids. A compliance candidate gets no documents, only the rule, the recorded results (TEST-QUALIFIER) and the product's cautions. Nothing is cached in this mode.
- **Hedging:** "verifier" can now be named in `HEDGED_AGENTS` (with `HEDGE_DELAYS=verifier=<ms>`). The default list does not include it.
- **Already settings, no code:** `VERIFY_THINKING=MINIMAL`; Flash-Lite as the verifier (`VERIFY_MODEL=gemini-3.5-flash-lite`, `VERIFY_THINKING=MEDIUM`).
- **An unverified alert (verifier timeout) is an active alert:** it has `shown_at` and is listed in the eval rows with `"unverified": true`. A drop in detection on that run is therefore not the timeouts dropping alerts.
- **Tests:** suite 1188 passed.

D-302: the vote arm (`JUDGE_ARM=vote`, off by default): model votes in place of the semantic code drops. The user wants every new direction tested as a switchable arm.
- **First pass:** the Flash-Lite agents with the semantic code drops off, the same as the R2 flagger. Schema and provenance checks stay.
- **Extra runs:** on a line where the first pass has a candidate (a non-negated, non-quoted violation, or a contradicted fact), the same agent runs twice more, in parallel, with the same prompt and inputs. They start as soon as the first pass returns. They send no second (hedged) request. `VOTE_TEMPERATURE` sets their temperature; empty means the model's default, 1.0 on Gemini 3, which Google advises keeping (D-008). A line with no candidate is not run again.
- **Agreement:**
  - A compliance vote is the same rule id or the same rule category, not negated or quoted, on a span that overlaps (one holds the other, or they share a word). Rules now carry their category: the market category, the law-pack `rule_category`, or "test_qualifier".
  - A fact vote is the same field, contradicted, with the same correction (equal numbers after normalisation; for a correction without numbers, half the words of the shorter one).
- **Votes:**
  - 3/3 keeps the rule's severity.
  - 2/3 keeps the candidate capped at MEDIUM.
  - 1/3 drops it, logged as "vote: 1/3".
  - A failed extra run is no vote. When both fail, the candidate is kept, unverified.
- **On the alert:** `votes`, and for facts `evidence_ids` (the relation arm's sentence ids). The eval rows carry both. The pipeline logs "vote: compliance/facts added N ms" per line.
- **`VOTE_CONFIDENCE=self`:** the compliance judge and the relation fact checker add a `confidence` (0-1) to each violation and claim. It is a log field only (in the eval rows' call outputs).
- **Tests:** `tests/test_vote.py`. Suite: 1206 passed.

D-303: switches for speech-to-text input. Pool 5 lines went through TTS (two voices) and our STT path. R3's code gates rose from 0.9% to 19.4% and 15.7% false alerts and from 0 to 5 and 3 wrong HIGH, for three reasons:
- STT drops quote marks.
- A brand comes out as a sound-alike, so the own-test check fails.
- A sentence is split at a pause.
R2 window (c58712d) on the same text gave 96.3 / 0.9 / 0. The user's direction: LLM judgment only, and code checks provenance and nothing else. The verify arm is the candidate, and no more code gates on meaning are added or tuned in guards mode.
- **`STT_AWARE`:** the compliance judge, the fact checker and the verifier are told the line is speech-to-text. Quote marks may be missing, so words such as "someone asks" start a quote. Names may be sound-alikes. Numbers may be misheard. A sentence may arrive in pieces. Prompt addenda `STT` in `prompts/design_arms.md`, with made-up names.
- **`CONTEXT_WINDOW_MS`:** the judges, the fact checker and the verifier read the finals of the last N ms (`recent`) as RECENT_TRANSCRIPT, in place of the last two; 0 keeps the last two.
- **`NUMBER_CHECK`:** the verifier may decide `check` for a fact whose only mismatch is one number speech-to-text may have misheard (`VerifyOutputC`, CHECK addendum). The alert is kept with `heard_check`. The host screen shows "CHECK WHAT WAS SAID" with the heard words, without the wrong mark. The eval rows carry `heard_check`.
- **Model notes (docs/VERIFIED.md):**
  - `gemini-3.5-flash` is a GA model id; its thinking levels were not checked here.
  - Flash-Lite and 3.8 Flash ignore a custom temperature, so `VOTE_TEMPERATURE` had no effect. The vote arm (3/3 on 112 of 130 alerts) stays off.
- **Tests:** `tests/test_d303.py` and a host-screen test. Suite: 1213 passed; frontend 179 passed.

D-304: each code rule that judges meaning gets an on/off switch, with defaults unchanged. The user wants every such rule compared with the model's own judgment and removed only if it hurts. The planning session measures them in bundles: the STT sets, clean text, the multi-product pool M1 (items 1, 2 and 7) and the comment set (items 8-12). Provenance, schema and safety rules are not switched.
1. **`SWITCH_ARM_NAME=false`:** a switch arms from the context judge's target and confidence alone; the next product's name need not be heard.
2. **No new switch.** `UTTERANCE_MERGE_WINDOW_MS=0` already judges every final as it comes, with no merge and no Q5 hold; add `CONTEXT_WINDOW_MS` (D-303) for the context. Transcript ids still keep each final judged once.
3. **`CORRECTION_CHECK=judge`:** the compliance judge's listed alerts are corrected with no word check, no replacement match and no late code correction. Arm B's quote-checked corrections need arm B's schema, so they stay with `DESIGN_ARM=B`.
4. **`QUALIFIER_ADDON=false`:** no late "in our in-house test" add-on.
5. **`VERBAL_CHECK=judge`:** the context judge alone answers with arm B's fields (numbers said, hedged; B addendum). A spoken answer's hold and the relink use them instead of the unsure regex and word coverage. The numbers must still be in the draft.
6. **`REFLEX_SCAN=false`:** no regex pre-scan and no provisional chip. With `REFLEX_ON_FAIL=card`, every line whose compliance call failed gets the check card, with no phrase. Arm C remains the bundle.
7. **`JUDGE_PRODUCTS=all`:** every show product's sheet and rules go to the judges, with no alias match. "The products the context judge names" is not possible without running it before the others, which adds latency.
8. **`COMMENT_PRODUCT=triage`:** a comment's product is triage's (code checks it is a product), otherwise the product on air. There is no alias match, no exclusion cues and no set-question override.
9. **`DRAFT_GATE=provenance`:** the draft code gate keeps citations, products and numbers (arm B's minimal gate), and a negated restricted mention passes. Gone are the length and sentence count, rule 6 (subject window) and rule 7 (in-house regex).
10. **No new switch.** `PREFILTER=pii_only` already exists.
11. **`GROUP_JOIN=model`:** no joining of the only open group of an intent, and no stem match of ingredients in the cached answer key. The model's group pick and the exact same question remain.
12. **`SHOUTOUT=judge`:** triage labels shout-outs (arm B's field and addendum); no regex.
- **Later (onboarding):** `lawpack._wording_for`, `release._rounded`, the lean check pinning, `brief._threshold`, the brief's restricted-phrase drop.
- **Tests:** `tests/test_d304.py` (18 tests). Suite: 1231 passed.

D-305: the model-only settings are the defaults (user decision: LLM judgment only, code checks provenance only). Every code path stays switchable for comparison; nothing is deleted.
- **Defaults:**
  - Facts and verifier: `JUDGE_ARM=verify`, `FACT_RELATION=true`, `VERIFY_EVIDENCE=window` (verifier gemini-3.8-flash LOW, `VERIFY_TIMEOUT_MS=3000`; a timeout keeps the alert, shown, marked unverified).
  - STT: `STT_AWARE=true`, `CONTEXT_WINDOW_MS=20000`, `NUMBER_CHECK=true`.
  - Live rules: `SWITCH_ARM_NAME=false`, `UTTERANCE_MERGE_WINDOW_MS=0`, `CORRECTION_CHECK=judge`, `QUALIFIER_ADDON=false`, `VERBAL_CHECK=judge`, `REFLEX_SCAN=false` (with `REFLEX_ON_FAIL=card`, every line whose compliance call failed gets the check card), `JUDGE_PRODUCTS=all`.
  - Comments: `COMMENT_PRODUCT=triage`, `DRAFT_GATE=provenance`, `PREFILTER=pii_only`, `GROUP_JOIN=model`, `SHOUTOUT=judge`.
  - `FACT_FIXES` and `FACT_GUARDS` are left as they were; they do not apply in verify mode.
- **New `STT_ENDPOINTING` (SHORT, STANDARD, SUPERSHORT), default SHORT:** STANDARD cut the pieces from 73 to 21 of 240 units at the same WER. It is measured end to end before any flip.
- **Multi-release shows:** with `JUDGE_PRODUCTS=all`, every release's law reaches every line. On a cream-and-kettle show, the made-up kettle line "It heals eczema while it boils" now meets the cosmetics rules. Only the judge and the verifier decide whether they apply, where before code withheld another category's law from a line that names no product of it (D-279). The demo show (two cosmetics releases, one law) is not affected. `JUDGE_PRODUCTS=named` restores the D-279 behaviour.
- **Tests:** the older tests script the code paths as written, so `tests/conftest.py` pins them (LEGACY, through the environment so `get_settings()` sees them too). `tests/test_d305.py` runs the shipped defaults end to end: a compliance alert through the verifier with no regex chip, a relation fact alert with evidence ids, the check card without the regex, a viewer question grouped, the demo show starting. Suite: 1236 passed.
- **Deploy:** Cloud Run revision live-studio-us-00002-hcg was built from the working tree while this change was uncommitted. Its runtime files (`config.py`, `providers/stt.py`) are the ones committed here, unchanged since 20:48:30. The image tag (app:5a9e124) names the commit before this one.

D-306: verifier slowness shown honestly (user decision): no weaker-model fallback, and an honest label when the AI does not answer.
- **Waiting:** when a line has a candidate, the host screen shows the small grey "checking" chip (the existing one, from the events `verify.started` and `verify.done`). Nothing covers the screen. The alert (HIGH overlay, MEDIUM banner, fact note) appears only when the verifier answers, so a HIGH overlay is always confirmed.
- **Timing:** `VERIFY_TIMEOUT_MS=5000`; the verifier is hedged with a second identical request at 2,000 ms (`HEDGED_AGENTS` includes `verifier`, `HEDGE_DELAYS` `verifier=2000`), and the first answer wins.
- **No answer after 5 s:** the alert is kept and shown, labelled "미확인 (AI 응답 지연) / Unverified (AI response delayed)". It carries `unverified_reason` (the failure type) on the host, the operator stack and the eval rows.
- **Operator:** a system card "AI 응답 없음 n건 · <cause>", with the most common cause: "Google 공용 용량 혼잡" for 504 and 429, "AI 응답 지연" for a client timeout, "AI 오류" otherwise. The card shows again after each new failure. The count by type is in the event `verify.health` and the state snapshot (`verify_health`). It is not on the host's screen.
- **Logging:** every call records `failure` (`http_504`, `client_timeout`, `http_429`, `other_error`) in the audit, and the eval rows carry it for every agent. This separates infrastructure failures from logic results.
- **Tests:** `tests/test_d306.py`, plus host and operator tests. Suite: 1245 passed; frontend 182 passed.

D-307: `eval_comment_flow.py` and `eval_verbal_post.py` crashed (StopIteration) on a base without run-sheets (D-278), so the comment and spoken-answer paths could not be checked under D-305. With no run-sheet and no `--release`, both scripts now start the demo show from its onboarded releases (as /api/demo/reset does). The cases' demo product ids (`cream_hydra_barrier`, `ampoule_deep_hydration`) are mapped onto the releases' products in show order, for the product on air, the seeded questions and a document change, which now re-indexes the show's own passages. A pack with a run-sheet (the test pack) or a `--release` runs as before. Tests: both scripts on the clean base. Suite: 1247 passed.

D-308: back to the measured configuration (c58712d's R2 window run). The STT ablation shows D-305's STT bundle is worse. On pool-5 STT text (voice A), R2 window gave 96.3 / 0.9 / 0 (detection / false alerts / wrong HIGH); the same plus `STT_AWARE`, `CONTEXT_WINDOW_MS=20000` and `NUMBER_CHECK` gave 96.3 / 11.1 / 5. GPT, Gemini and Sonnet agreed to roll back and to ship no unmeasured defaults on the comment side.
- **Kept:** `JUDGE_ARM=verify`, `FACT_RELATION=true`, `VERIFY_EVIDENCE=window`, verifier gemini-3.8-flash LOW. The code-drop gates stay off, because verify mode bypasses them.
- **Back to the pre-D-305 values:** `STT_AWARE=false`, `CONTEXT_WINDOW_MS=0`, `NUMBER_CHECK=false`, `UTTERANCE_MERGE_WINDOW_MS=3500`, `SWITCH_ARM_NAME=true`, `CORRECTION_CHECK=words`, `QUALIFIER_ADDON=true`, `VERBAL_CHECK=code`, `REFLEX_SCAN=true`, `JUDGE_PRODUCTS=named`, `COMMENT_PRODUCT=code`, `DRAFT_GATE=full`, `PREFILTER=full`, `GROUP_JOIN=code`, `SHOUTOUT=regex`. Each goes back to model-only only after its own on/off measurement wins.
- **Display (D-306) kept:** the checking chip, the HIGH only after the verifier confirms (the regex chip is back, and it is only the grey chip), the 5 s timeout, the "unverified (AI response delayed)" label, the operator's cause card and the per-call failure type.
- **The verifier hedge is a switch, off by default:** add "verifier" to `HEDGED_AGENTS`; its 2,000 ms delay stays in `HEDGE_DELAYS`.
- **Tests:** suite 1247 passed.

D-309: the single arm (`JUDGE_ARM=single`, off by default). The user asked why we do not use only the strong model. The user's latency rule is that an alert must appear within 3-5 s after the line ends, which a second stage struggles to meet.
- **Models:** the compliance judge and the fact checker run on `SINGLE_MODEL` / `SINGLE_THINKING` (default gemini-3.8-flash LOW). The cells are gemini-3.5-flash-lite HIGH and gemini-3.8-flash LOW. A new `COMPLIANCE_MODEL`, and the existing `FACTS_MODEL`, override the model per agent. The context judge stays on Flash-Lite MINIMAL.
- **Pipeline:** no verifier, no code drops (as in verify mode: provenance checks only). The compliance call's deadline is `VERIFY_TIMEOUT_MS` (5 s). The fact checker keeps the whole documents in its cache (FD).
- **Severity:** the judge may lower a HIGH rule to MEDIUM for a lesser form of the claim (`SINGLE` addendum), as the verifier does. Otherwise it is the rule's severity, never raised.
- **Display:** an alert made unverified by a failed judge call now carries the call's failure type (`unverified_reason`), so it reads "unverified (AI response delayed)". This applies in every arm.
- **Window mode (verify):** when the flagger's quote matches no document sentence, the verifier gets no documents for that fact. This is now logged and listed in the eval rows' `dropped` as "verifier window: no sentence matches the quote".
- **Eval rows:** each alert carries `ms_to_created` and `ms_to_shown`, from the final received to the alert created and to it shown (active), for p50 and p95 alert latency per arm.
- **Tests:** `tests/test_d309.py`. Suite: 1253 passed.

D-310: `COMPLIANCE_DOCS` (off by default), the design for a Flash-Lite-only judge (the user and the planning session). gemini-3.8-flash is ruled out by speed (about 3.5 s mean in the path) and cost.
- **Flash-Lite single cells need no code:** `JUDGE_ARM=single`, `SINGLE_MODEL=gemini-3.5-flash-lite`, `SINGLE_THINKING=LOW` or `MEDIUM`.
- **Why the documents:**
  - The compliance judge's prefix (system plus rules) is about 3.3k tokens on the demo cream, under Gemini 3's 4,096-token cache minimum, so no cache was ever made.
  - On the STT set, 14 of 22 Flash-Lite false candidates on safe lines were compliance ones. The biggest class was a TEST-QUALIFIER raised when the line did name the tester, but speech-to-text misheard the name.
- **What it does:**
  - With the switch on, the prefix also holds the on-air product's documents: a PRODUCT_DOCUMENTS block of its passages and its files' text, with the release files as cached parts (the fact checker's FD files).
  - The prefix is then about 5.8k tokens on the demo cream (more with files), so it is cached.
  - A DOCS addendum says the documents are not rules: use them to recognise a sound-alike tester, lab, brand or ingredient.
  - Every product's compliance cache is warmed at the start of the show (the warm-up already ran per product for the fact checker).
  - In a multi-release show the documents are the on-air product's.
- **Eval rows:** every agent's call now carries `usage` (prompt, output, thoughts, cached).
- **Tests:** `tests/test_d310.py`. Suite: 1257 passed.

D-311: `SINGLE_FACTS_THINKING` (empty means `SINGLE_THINKING`) sets the fact checker's thinking level apart in the single arm, so the compliance judge can run at MEDIUM and the fact checker at LOW on Flash-Lite. Why, from the Flash-Lite results on STT pool 5:
- **LOW on both agents:** the alert showed in 1.4 s on average (p95 2.4-2.6 s). False alerts were 10-20% and wrong HIGH 4-13, almost all from the compliance judge, and `COMPLIANCE_DOCS` made wrong HIGH worse at LOW (4 to 11).
- **MEDIUM on both:** wrong HIGH 0 and false alerts 9.3%, but the fact checker timed out often (47 client timeouts).

D-312: `FACT_PROMPT=v2` (default `v1`, today's prompt) switches the fact checker to `prompts/fact_relation_v2.md`. Why: the best arm so far (single, Flash-Lite, compliance MEDIUM, facts LOW, STANDARD endpointing) passes wrong HIGH and latency, but false alerts are 6.5-8.3%, nearly all from the fact checker, and Flash-Lite at LOW used no thinking tokens, so the order of its output fields matters. Prompt and schema changes only; no code gate or drop (the user's rule).
- **Only what the host asserts:** a question read out, or words attributed to someone else, is not a claim unless the host agrees in the same line. Such a line gets no claim, or `consistent`/`uncertain`, never `contradicts`. A rhetorical question the host clearly asserts is still a claim. New example: a read-out viewer question gives empty claims.
- **Sound-alike values are `uncertain`:** a value that differs from the documents only as speech-to-text can produce it (number words merged into one number, a sound-alike proper name) is held back. A clearly different value still contradicts. The "too coats" rule stays `consistent`. New example: a merged number gives `uncertain`.
- **The documents' value first:** the schema (`FactRelationOutputV2`) adds `source_value` after `evidence` and before `relation`, and the relation is decided by comparing `stated_value` with it. It is logged in the raw call output, in the eval rows, and in the "relation uncertain" drop entry. `VOTE_CONFIDENCE=self` adds no confidence field under v2.
- **Compliance judge:** the same switch adds the `V2: compliance_judge` addendum: a tester or lab named in a sound-alike spelling still states the qualifier.
- **Tests:** `tests/test_d312.py`.

D-313: `FACT_PROMPT=v3` is `fact_relation_v2.md` plus one rule, in `prompts/fact_relation_v3.md` (v2 stays fixed for comparison). Why: v2 (D-312) cut false alerts on STT pool 5 from 6.5 / 8.3% to 0.9 / 1.9% (voices A / B), with detection 97.2 / 98.1%, but it made a new miss in both voices. "Someone says <a wrong term>." followed by "Correct." gave no claim on either line: the first is someone else's words, and the second has no fact of its own, because v2 checks only facts the host states or endorses in the line.
- **The rule:** a line that endorses what the last line of RECENT_TRANSCRIPT reported or asked ("Correct.", "Yes, that's right.", "Exactly.", "Yes, you can.") makes that line's facts the host's own claims, with `span` from the previous line's words. A rejection ("No.", "Not true.") gives no claim.
- **Examples:** a made-up pair sits next to Example I, the read-out question. Example J is an endorsement that contradicts, with the right value. Example K is the same line rejected, with empty claims. The merged-number example is now L.
- The schema and the compliance line are v2's. Prompt only, no code.
- **Tests:** `tests/test_d312.py` (now v1 / v2 / v3).

D-314 (eval): `JUDGE_TEMPERATURE` and `JUDGE_SEED` set the sampling of the live judges' calls: compliance_judge, fact_checker and context_judge, including the single arm. Both are empty by default, and then nothing is sent (D-008). Why: identical STT text got different verdicts across runs. A contradicts with stated == correct came 2 times in 8, and a compliance HIGH 6 times in 8, so one flip moved false alerts by 0.9 points and arms could not be told apart.
- **Where it is set:** in `LLMClient.call`, for those agents only. A vote run's own temperature is kept. Onboarding, brief, comments and the verifier are untouched. Each `AgentCall` and each eval row records the `temperature` and `seed` that were sent.
- **Probe (VERIFIED 2.3):** on `gemini-3.5-flash-lite`, Vertex accepts both settings. It ignores `temperature` (temperature 0 still gave 5 different answers out of 5) and applies `seed` (1 answer out of 5).
- **Limits:** a seed fixes the answer only for an identical request. A line whose prompt differs between runs (RECENT_TRANSCRIPT, promo state, a split merged differently) can still flip. A hedged second request with the same seed repeats the first. With `JUDGE_ARM=vote`, a seed would make the extra runs identical.
- **Tests:** `tests/test_d314.py`.

D-315: the Hub's approved-product picker is a list of product cards, and a show lost to a server restart is said plainly. Why: the user found the native select (one long label, a "Then" row of bare checkboxes) hard to read. On the cloud (STORE=memory, scale to zero) a session id kept in the URL gave every screen "session ses_... not found".
- **Cards:** each approved release is a button (`aria-pressed`) showing the brand, the product name, market chips, version and approval date, and the brief status chip ("brief running" with a spinner, "ready" when done). The cards picked, in order, are the line-up: numbered badges, a "1. Serum → 2. Ampoule" summary with remove buttons and Clear, at most 3 (D-279; the other cards are disabled when 3 are picked). One primary button, "Start a show with N products", is disabled with no pick or while busy. The brief-running note shows when a picked release's brief runs. The grid is auto-fill, so it is one column at phone width. Korean strings are in KO_HUB. The market and language selects were dropped by the planner's correction.
- **Stale session:** `request()` reports a 404 `session_not_found` to the app, which shows "This show ended (server restarted). Start a new one to keep going." with one button instead of the screen and its raw error. The button drops `?session=` from the URL, so the app takes `/api/demo/current`, the demo show (made when none is left).
- **Tests:** `src/screens/screens.test.tsx` (cards, line-up order, max 3, remove, clear, brief note, request body) and `src/app/router.test.tsx`. The screens test's fetch mock now answers `[]` for the release list, which also removes the "rows?.some is not a function" errors the old Hub tests logged.

D-316: the demo console's Mic section has a speech-recognition language select, so the user can test by speaking a JAPAC language. Unmeasured: the judges, prompts, language packs and reflex lists are unchanged, and lines in another language go to the same judges.
- **UI:** a select next to Start/Stop lists English (en-US, the default), 한국어 (ko-KR), 日本語 (ja-JP), 中文(简体) (cmn-Hans-CN), 中文(繁體) (cmn-Hant-TW), Bahasa Indonesia (id-ID), Bahasa Melayu (ms-MY), ไทย (th-TH), Tiếng Việt (vi-VN), Filipino (fil-PH) and 자동 감지 (auto), each name in its own language. Every option except en-US is marked "실험 중 · 정확도 미측정". The choice is kept per browser (`ls.mic.lang`) and locked while the mic runs. The shared mic client sends it, so the host screen's mic uses it too.
- **Transport:** the audio WebSocket opens with `?lang=<code>`. `audio_ws.py` uses the code only when it is on the allow-list (`STT_CHOICES`); anything else falls back to `STT_LANGUAGE`, then the session pack's code (as before). `first_request` now puts the caller's code first.
- **Probe 10/7 (chirp_3, region us, our recognizer config, SHORT and STANDARD endpointing, 1.5 s of silence per stream):**
  - All ten language codes opened a stream with phrase hints.
  - `auto` answered 404 "Requested entity was not found" with phrase hints and opened without them, so `auto` streams get no phrase hints.
  - Silence checks only that the config is accepted, not recognition quality.
- **Logs:** a line at open says the language, the code asked for and the hint count. A line for each final gives `stt final <session> <transcript_id> lang=<code>`, next to the existing `final ...: '<text>'` line. The listening status message carries `lang`.
- **Tests:** `tests/test_audio_ws.py` (ko-KR, auto without hints, an unknown code, no code) and `src/app/prefs.test.ts`.

D-317: the mic language select of D-316 shows only languages with measured judging accuracy by default (`MEASURED_LANGUAGES` in `frontend/src/app/prefs.ts`, today en-US alone). With one language the select is hidden. Why: a judge who picks an unmeasured language and sees poor alerts would count it against the product.
- **Labs mode:** opening any page with `?labs=1` turns on labs mode for that browser (`ls.labs`); `?labs=0` turns it off. In labs mode every D-316 code appears, still marked "실험 중 · 정확도 미측정".
- **Stored choice:** outside labs mode, a stored unmeasured choice falls back to en-US, so the mic never sends it.
- **Backend:** the allow-list is unchanged, so internal tests work on the deployed build.
- **Measuring a language:** add its code to `MEASURED_LANGUAGES` (one line).
- **Tests:** `src/app/prefs.test.ts`.

D-318: fixes from codex's review of fd62170..HEAD, made before the deploy.
- **D-316, mic language:** the mic sent `?lang=en-US` even with no choice, which overrode a server `STT_LANGUAGE`. It now sends `lang` only when this browser picked one. The select gained "Session default" (no `lang` sent), so the server's setting, then the pack's code, apply as before. Test: `test_d316_with_no_choice_the_server_setting_keeps_its_language` and `test_d316_the_recognizer_s_language_code`.
- **D-315, "Start a new show" with a session from `/demo/current`:** the button returned to the ended screen, because nothing fetched the session again. `useSessionId` now has `refresh()`, which the button calls.
- **D-315, stale-session callback:** it had no session identity, so a late 404 from a session the page had left replaced a valid screen. `request()` now passes the session id from the path (`/sessions/<id>` or `?session=<id>`), and the app acts only on its current session.
- **D-314, sampling settings:** a bad `JUDGE_TEMPERATURE` or `JUDGE_SEED` raised ValueError inside a judge call. Settings now check them at load, so a bad env fails at startup.
- **Tests:**
  - `src/app/router.test.tsx`: a replacement session loads for a URL session and for a `/demo/current` session; a late 404 is ignored.
  - `tests/test_d312.py`: the v3 endorsement and rejection pair through `run_case`, single arm.
  - `tests/test_d314.py`: bad values fail at startup.

D-319: the approved-products picker of D-315 moves out of the Hub hero into a popover. Why: the user saw the cards at the top of the hero after the deploy and called it "주객전도"; they are not the Hub's main action.
- **Hero row:** the main actions stay as before (Open Studio, Try it with a sample product, Onboard a new product). The row gains one secondary button, "Start with approved products ▾" (승인된 제품으로 시작), with a count badge. It is hidden when there are no approved releases.
- **Panel:** the button opens an anchored panel, a styled dialog and not a native select. It holds the same rows (brand, name, market chips, version and date, brief chip), now compact and in one column. The line-up behaviour of D-315 is unchanged: click order, numbered badges, at most 3, the summary with × and Clear. The "Start a show with N products" button is at the bottom of the panel.
- **Behaviour:** Escape, an outside pointer-down and a started show close the panel. Focus moves to the first row on open and back to the button on close. The button carries `aria-haspopup`, `aria-expanded` and `aria-controls`, and the rows keep `aria-pressed`.
- **Phone width (under 700 px):** the panel becomes a bottom sheet, full width, at most 70vh and scrolling.
- **Tests:** `src/screens/screens.test.tsx` adds the open step, focus in and out, Escape, an outside click and closing on start.

D-320: the judge test drive (D-238) speaks the host's lines into our speech-to-text path instead of injecting text, so a judge hears the host, sees the STT caption, then the alert, with the real latency. Comments in the scene are unchanged.
- **Speech:** Cloud TTS voice `en-US-Chirp3-HD-Leda`, LINEAR16 16 kHz mono WAV, which the STT stream takes and the browser plays. Each line is cached on disk by the hash of voice and text (option (a), from the scene's actual line text).
  - Probe 10/7: five lines in parallel took 1.1 s warm and 6.7 s on a cold laptop client.
  - The host lines are made before the scene starts, waiting at most 5 s. A line not ready by then keeps going in the background, or is made when it is said.
  - The host_answer line (with the verified draft) is made at that moment.
- **Server (`testdrive.Voice`):** one STT stream per test drive, set up as the mic's (`audio_ws.stream_setup`: phrase hints, language).
  - The voice writes 100 ms frames in real time: each line's PCM, and silence between lines.
  - Finals go to `utterances.submit(source="mic")`, the normal path to the judges, logged as `testdrive stt final`.
  - When a line's streaming starts, the session emits `testdrive.audio` {url, text, duration_ms}.
  - Probe 10/7, real TTS into chirp_3: both lines came back word-for-word, 1.4-1.6 s after the line ended.
- **Fallbacks:** the scene never stalls.
  - A line with no final within 6 s of its audio ending is injected as text (`testdrive stt fallback`).
  - Without speech-to-text (STT_PROVIDER=mock), or when the stream cannot open, the scene plays as text as before.
  - A line whose speech cannot be made is injected as text.
  - The 6-per-hour cap and the one-at-a-time rule are unchanged.
- **Browser:** the Studio plays each `testdrive.audio` line when it arrives. A small pill, "AI voice (demo)", with a mute toggle (kept per browser) shows from the first line. If the browser refuses autoplay, the toggle reads "Sound blocked: click to allow". `GET /api/testdrive/audio/<key>.wav` serves only cached keys.
- **Fixed on the way:** the browser never subscribed to `line.check` (D-298), `verify.started` / `verify.done` / `verify.health` (D-306) or `feed.updated`, so those showed only after a reload. They are in `EVENT_TYPES` now. A backend test fails when an emitted event type is not subscribed.
- **Not verified:** that the Cloud Run service account may call Cloud TTS. The API answered for the project from this laptop. If the service account is refused, every line falls back to text and the log says `testdrive tts failed`.
- **Dependency:** `google-cloud-texttospeech`.
- **Tests:**
  - `tests/test_d320.py`: speech goes through STT as `mic`; the fallback; no STT or no TTS; the audio endpoint; event subscriptions.
  - `src/app/state.test.ts`.

D-321: two changes after the D-320 pre-test, in which the planner ran each host line through Cloud TTS (the Leda voice) and chirp_3 10 times. The 10 runs gave the same text each time.
- **The viewer in the test-drive scene is now "Sarah", not "Siti".** STT heard "Siti" as "City" with STANDARD endpointing and as "CD" with SHORT, 10 runs out of 10. Only the scene script changed: the comment author and the host's "... asked about pregnancy." line.
- **`deploy/cloudrun.sh` now sets `STT_ENDPOINTING=STANDARD`.**
  - With SHORT, the cloud's setting until now, 3 of the 4 demo lines split into two or more finals in every run, and words changed ("welcome to Today", "Help skin").
  - With STANDARD, lines 1-3 came back word for word, with the final 1.1-1.5 s after the audio ended.
  - On pool 5, STANDARD cut split lines from 73 to 21 and lowered false alerts. The latency pass line still held.
  - The code default (SHORT) is unchanged. The setting takes effect when the user deploys.

D-322: fixes from codex's review of D-320 and D-321, made before any push or deploy.
- **Admission:** `/testdrive/{job}/go` now plays only the job its `/start` admitted, once (`claim`), and never next to another drive. An admitted start counts as busy for 15 minutes. Before, repeated `/go` calls, or any finished onboarding job, could start paid drives past the cap.
- **One outcome per line:** a final goes to the line whose audio it came from. The final's speech end must fall between the line's audio start and its end plus 1.5 s. Each line ends with its finals or the text fallback, never both. A late final after the fallback is dropped and logged. A final from another line no longer stops a line's fallback.
- **Stopping:** a show ended early (by the operator) stops the scene within a second. The voice's `close()` cancels and awaits every task it owns (the pump, the listener, the watchers) and closes the stream.
- **One speech-to-text stream per show:** while the voice holds a session, the mic WebSocket answers "The test drive's AI voice is using speech recognition for this show."
- **Per-line deadline:** the speech for a line must be ready within 4 s of the line being due, else the line goes in as text.
- **Checking chip:** `verifying` is keyed by line and kind, so a fact check finishing first no longer clears the chip while the compliance check runs.
- **Mute:** a line that arrives while muted counts as played, so unmuting affects only later lines.
- **Tests:**
  - `tests/test_d320.py`: the late final, a final from another line, slow speech, an early end, the mic guard.
  - `tests/test_onboarding.py`: `/go` admission.
  - `src/screens/studio.voice.test.tsx`: mute and unmute.
  - `src/app/state.test.ts`: the chip per kind.

D-323: fixes from codex's second review of the test drive (46d9a05).
- **A failed `/go` can be retried:** when approval or the show's start fails, `release` gives the job its admission back. Before, every retry got 429.
- **A final spanning two lines covers both:** a final that also holds most (60%) of the words of the lines just before its own ("A B" heard as one) marks those lines as heard. None of them falls back to text and is judged twice. A final with another line's words alone still leaves a line unheard, so that line still falls back.
- **One frame of grace at a line's start:** speech-to-text stamps a frame at the end of its audio, and the voice stamps a line at its first frame's write. A final up to one frame before the line's start now belongs to it.
- **The voice owns its warm-up:** the scene's speech made ahead runs as tasks the voice owns, cancelled when it closes. A line waiting for its speech gives up when the show ends: a watcher checks every 0.25 s.
- **The hold starts with the drive:** the voice holds the session's speech-to-text from the start of the drive, before the warm-up, so a mic cannot connect in between.
- **Tests:** `tests/test_d320.py` (`d323_*`).

D-324: the test drive's final-to-line matching is simpler. Codex's third review showed that the D-323 rules hid lines. Under the 60% word-overlap rule, a risky line STT did not hear counted as heard when the next line used nearly the same words, so it never reached the judges. The 100 ms start grace let the next line claim a final at the boundary. Both rules are gone.
- **Silence between lines:** lines are at least 1.5 s apart (`GAP_MS`). With STANDARD endpointing, each line is then finalized on its own.
- **One window per line:** each line owns one window, from its audio's start to the next line's start. A boundary belongs to the earlier line. A final goes to the window its speech ended in.
- **Fallback:** a line with no final in its window 6 s after its audio ends goes in as text. A later final in that window is dropped and logged.
- **Show end:** the end of the show now also ends the wait for the warm-up (up to 5 s before).
- **Tests:** `tests/test_d320.py` covers codex's two cases (an unheard line next to a near-identical heard line falls back; a final at the boundary is the earlier line's, and the unheard later line falls back), the gap, and the end during warm-up. It keeps the late-final and failed-`/go` tests.

D-325: `FACT_PROMPT=v4` is `fact_relation_v3.md` plus one rule, in `prompts/fact_relation_v4.md` (user-approved 10/7, prompt only). The default stays v1, and v2 and v3 are unchanged for comparison.
- **The rule:** the documents may attach a condition to a value: at manufacture, under laboratory conditions, per serving, for a given size or market, before or after a date. When the host states the value without that condition, it is not the same fact. The relation is `contradicts`, and `correct_value` carries the condition. `source_value` carries the condition too. When the host keeps the condition, or the documents attach none, values are compared as usual.
- **Examples (made up):**
  - L: the documents say "10 million per sachet at manufacture"; the host says "each sachet has ten million live cultures". Result: `contradicts`, correct "10 million per sachet at manufacture".
  - M: the host keeps the condition. Result: `consistent`.
  - v3's merged-number example is now N.
- **Tests:** `tests/test_d312.py` (v1 to v4).

D-326: the v4 rule of D-325 is narrower (fact_relation_v4_v2). Codex's review: as written, the rule raised a correction whenever the host left out a condition, size and market included. "It costs S$39" right after the 50 mL size was named is consistent with "50 mL: S$39".
- **When the condition counts as kept:** the line, RECENT_TRANSCRIPT, CURRENT_PRODUCT or its variant, or the show's market already establishes it.
- **When it contradicts:** only when the line asserts the value in a way the condition makes untrue or misleading. Examples: live cultures "now" against "at manufacture"; a laboratory result stated as everyday performance.
- **New counter-example N:** the 50 mL size was named in the line before, and the host says "And it costs thirty-nine dollars." The relation is `consistent`. The merged-number example is now O.
- The default stays v1.

D-327: `STT_HINTS=record` (default `base`, today's hints) adds each on-show release's own terms from its approved record to the speech hints. Why: STT still mishears product-specific words, such as a lab name ("Tessel Quay" heard as "Tessle Keys"), test and report names, and pack sizes said in words. Live path only: the existing record and brief are read, and nothing in onboarding or the brief changes.
- **Terms (`audio_ws.record_terms`):** they come after the brief glossary and the base names, under the same 500 cap, deduplicated case-insensitively, in this order:
  - brand and product;
  - short names and variant names;
  - names and ids in the test results' qualifier, statement and conditions (labs, testers, panels, certificates, report ids);
  - variant sizes in figures ("30 ml", "24 sachets");
  - proper names in the key facts.
- **What counts as a name:** two or more capitalised words, a capitalised word that does not start its sentence, or an id with digits ("TQ-2291", "ISO 22716"). Prices, bare numbers and sentences are left out.
- **Boost:** `STT_HINT_BOOST` (0-20, empty means none, as today) puts one boost on the phrase set.
  - Probe 10/7 (chirp_3, region us): boosts 5, 10 and 20 were accepted.
  - On a test line ("…confirmed by Tessel Quay Labs in report TQ-2291"), the hints alone fixed the name, which was "Tessco Labs … TQ2291" without hints. The boost changed nothing there.
- **Eval hook:** `audio_ws.phrases_for_release(ctx, release_id, mode=None, market=None, lang=None)` returns exactly the hints a one-release show's stream sends (the mic and the test drive), brief glossary included. A test checks it against the stream.
- **Logs:** the hint log at stream open now names `STT_HINTS` and the boost.
- **Tests:** `tests/test_d327.py`.

D-328: two switches from the pool 6 failure, both off by default (user-approved 10/8). The model decides; code only waits.
- **`REPORTED_HOLD` (needs `FACT_PROMPT` v2-v4):**
  - The fact checker's schema becomes `FactRelationOutputH`. It adds `previous_line` (`endorses`, `rejects` or `unrelated`: what this line does with the facts the last line reported or asked) and, per claim, `attributed` (`host`, or `other` for words reported from a viewer or another person, or a question put to someone), both decided first.
  - The `HOLD: fact_checker` addendum has three made-up examples: a reported wrong amount, its rejection, and a co-host's question.
  - A contradiction attributed to `other` is held. The host sees the grey checking chip (`verify.started`, kind `reported`) instead of the alert.
  - When the next line's fact check returns, the hold is settled:
    - `rejects`: the alert is dropped, logged as "held alert dropped: rejected by next line".
    - `endorses` or `unrelated`: the alert shows (one alert; the endorsement's own claim joins it).
  - With no next line, the alert shows after `REPORTED_HOLD_MS` (2500). When a next line was heard but not yet checked, the hold waits for that check, up to two fact timeouts more: a missed risk is worse than a late one.
  - Each hold logs its duration. The alert's `shown_at` is the release time, so `ms_to_shown` in eval rows carries the cost.
  - `host` claims are not held.
  - `drain()` (eval, tests) lets each open hold run its time.
- **`COMPLIANCE_NEG`:** the `NEG: compliance_judge` addendum. A line that warns against a risky use or negates a claim ("Don't skip meals and rely on this bar instead", "Please don't stop your medicine because of this tea") is not that claim. It is listed only with `is_negated = true`, which never alerts. A line breaks the rule only when it asserts or recommends the claim.
- **Not addressed:** overlapping speech. The user treats one mic hearing one of two speakers as out of scope.
- **Tests:** `tests/test_d328.py` (through `run_case`: rejected, endorsed, no next line, an unrelated next line, a host claim; the chip; the switches).

D-329: fixes to D-328's hold, from codex's review (four P2s).
- **Show end:** a hold still open when the show ends now shows its alerts (the same rule as a missed next line: a missed risk is worse than a late one) and sends `verify.done`. Before, it was neither shown nor dropped.
- **Only the next line settles a hold:** a hold is settled only by the fact check of the line right after it, or by the timeout. A later line's check no longer releases it. The timeout keeps waiting while that next line has been heard and its check is not back, up to `REPORTED_HOLD_MS` plus two fact timeouts. A next-line check that came back before the hold started is applied when the hold starts.
- **Per claim:** `previous_line` is now a list of {product_id, field, stance}. It names each fact of the last line that this line endorses or rejects. A rejected claim is dropped and an endorsed one shows. A held claim this line does not name stays held until the timeout, so correcting only the price no longer loses the amount alert. An empty list means this line does neither. The HOLD addendum and its examples changed to match.
- **Latency:** an endorsed alert keeps the line it came from. The endorsing line's same claim (product and field) joins it instead of re-showing it on the later line, so `ms_to_shown` counts the hold.
- **Tests (`tests/test_d328.py`):** a partial rejection; the completion order L1, L3, L2; an endorsement's latency (2000 ms); two holds in a row; a timeout waiting for the next check up to the cap; the show ending with a hold open.

D-330: the hold of D-328/329 works on claim subjects, not fields, after codex's second review.
- **Matching by the claim's words:** each `previous_line` item now carries `span`, the last line's words for that fact. A held claim is settled only by the item of its product and field whose words are the claim's (`span` or `stated_value`, one inside the other, case and punctuation aside). When the claim is the only held one of that product and field, a matching product and field is enough. So rejecting iron no longer drops a held zinc claim on the same field.
- **One subject:** two outputs are the same subject when they have the same product and field and share an evidence sentence, or, without evidence ids, the same passage.
- **Endorsement:**
  - The endorsing line's own claim joins the endorsed alert only when it is the same subject. Its other contradictions (zinc next to an endorsed iron) still alert on that line.
  - When the endorsing line's check comes back before the original line's, its endorsed contradiction is made on the original line at once, so the delay counts from there.
  - An endorsed alert already shown on the endorsing line moves to the original line and keeps its shown time.
- **Retiring a hold:** when the hold times out, a held claim whose subject a later line stated consistently (that line's own `supported` output) is retired, logged as "held alert retired: corrected later".
- **Known limit (unchanged, D-117):** `apply_fact_check` keeps one note per (product, field, passage). Two wrong amounts cited from one passage still share a note.
- **Tests (`tests/test_d328.py`, `d330_*`):** the same-field partial rejection, the endorsing line's check first (latency 2000 ms on the original line), an endorsement next to a new claim, and a retired hold.

D-331: `FACT_PROMPT=v5` (`prompts/fact_relation_v5.md`) is v3 plus a `stance` per claim. Agreed by the planner with GPT, Gemini and the critic; user-approved 10/8. The default stays v1, and `REPORTED_HOLD` and `COMPLIANCE_NEG` stay off: on pool 6 the hold brought back the quote false alerts.
- **Schema (`FactRelationOutputV5`):** `stance` comes right after `span`, before evidence, `source_value` and `relation`, so the model decides it first. Its values are `HOST_ASSERTS`, `HOST_ENDORSES` and `REPORTS_OR_ASKS`. A `REPORTS_OR_ASKS` claim takes the relation `not_checked`.
- **Per claim, not per line:** "A viewer asks if it has 80 mg, and yes, it does" is `HOST_ENDORSES`, so it is still checked. v3's endorsement of the previous line ("Correct.") is `HOST_ENDORSES` too.
- **Code reads the field only:** a `REPORTS_OR_ASKS` claim never alerts, whatever its relation. When the model also wrote `contradicts`, it is logged in the eval rows' `dropped` ("reported or asked: not checked").
- **Guard against over-extraction:** "List only the facts in the line; adding `stance` must not add claims." Each relation call logs its claim count and stances ("fact claims N <prompt version>: {stance: n}") for the comparison with v3.
- **Examples (made up):**
  - v3's examples now carry a stance. Example I lists its read-out question as `REPORTS_OR_ASKS`.
  - New examples:
    - M: a viewer's reported amount, `REPORTS_OR_ASKS`.
    - N: the compound line, `HOST_ENDORSES`, contradicts.
    - O: a tag question the host asserts, `HOST_ASSERTS`.
    - P: a co-host's question, `REPORTS_OR_ASKS`.
- **Tests:** `tests/test_d331.py`.

D-332: UI fixes from the planner's QA of cloud revision 00005 (UI only, no judge change).
- **/host, /operator and /viewer opened without ?session showed an empty show ("NOW —", "No product on air"):**
  - Cause 1 (frontend): `cachedResource` fetched only on first mount, so when the session id arrived later the session's catalog was never loaded. It now fetches per resource.
  - Cause 2 (backend): `/demo/current` returned the newest session of any kind, ended or not, test drives included. It now returns the newest demo show that has not ended, or makes a new one.
  - With no required points, the host's status line no longer says "All required points said".
- **Studio host pane:** "Host + Operator" is 68/32 (was 60/40), and the host screen in a Studio pane never scales below 0.7. Cautions measured 10.5 px (was 9 px; QA saw 7-8 px) at 1440×900 in headless Edge.
- **Cautions:** the prompter shows the first 4 in record order, the rest behind "+N more" / "Show fewer".
- **Demo console:** columns shrink with the window (`minmax(0, …)`), wrap to two below 1100 px, and the select and mic text stay inside. Headless Edge with ?labs=1 at 1440, 1280 and 1024 px showed no horizontal scroll, and the select fit the window.
- **Operator:** the "LLM –k tokens/h" chip is hidden until there is a number.
- **Hub picker:** each product is listed once, at its latest version. Older versions sit behind "Older versions (n)" and carry an "older version" label. The count badge counts products.
- **Viewer without a product image:** the card shows the brand's initials, not an empty frame.
- **Tests:**
  - `tests/test_d332.py` and `src/app/router.test.tsx`: the catalog of a late session id; this test fails without the fix.
  - `src/screens/host/host.test.tsx` (+N more), `src/screens/ui_qa.test.tsx` (points line, token chip), `src/screens/screens.test.tsx` (older versions), `viewer.test.tsx` (initials).

D-333: `FACT_PROMPT=v6` and `COMPLIANCE_ENDORSE`, both prompt-only and off by default (user-approved 10/8, failure classes from fresh pool 7 with v5).
- **`FACT_PROMPT=v6` (`prompts/fact_relation_v6.md`):** v5 with the same schema (`FactRelationOutputV5`), plus three rules.
  - An answer takes its subject from the question. When the last line asks a question (either host) and this line answers it, the fact is about the question's subject and is compared with that subject's value. This also holds for a sentence cut in two by speech-to-text. The answer is `HOST_ASSERTS`.
  - A rejection that states a replacement value ("No, it's 106 now.") is a `HOST_ASSERTS` claim and is checked. A plain "No." still gives no claim.
  - A question stays `REPORTS_OR_ASKS` even when a host or co-host asks it.
  - Made-up examples Q-T: the 3-pack price answer, the split "Each stick holds" / "13.5 grams", the rejection with a new price, and a co-host's question.
  - Claim counts are logged as for v5.
- **`COMPLIANCE_ENDORSE`:** the `ENDORSE: compliance_judge` addendum. When this line endorses what the last line reported or asked ("A viewer says it treats eczema." then "Yes, that's what it does."), the judge treats the endorsed claim as this line's own claim and judges it with the RULES given (`is_quoted = false`). A rejection is not a violation. It never invents or widens a rule.
- **Tests:** `tests/test_d331.py` (`d333_*`).

D-334: two switches for a meaning that spans two finals ("For 30 mL of concentrate, how much water goes in?" then "90 mL"), both off by default, on top of `FACT_PROMPT=v5` (user-approved 10/8; QUESTION_HOLD is the user's design).
- **`QUESTION_HOLD` (`QUESTION_HOLD_MS` 2500):**
  - A final that ends with "?" is held. The next final within `QUESTION_HOLD_MS` joins it, and all three judges see the pair as one utterance. The fact checker shows it as "question / answer". The D-285 merge path is reused: the held question is never judged alone, and the answer is judged only inside the pair.
  - With no answer in time, the question is judged alone, as today.
  - It is a scheduling rule on STT punctuation only; the models decide the meaning. Each question final is logged ("question final … (n of m finals)") so chirp_3's "?" can be checked, and so are the pairing and the wait.
  - Eval rows get `ms_from_first_final`, measured from the first final of the utterance an alert was judged in. It shows the wait of a held question or fragment. `ms_to_shown` keeps its meaning (from the alert's own final), so earlier runs stay comparable.
- **`CONTEXT_JUDGE`:**
  - The fact checker's message has a CONVERSATION block (the last 3 finals, oldest first, the line to check last) in place of UTTERANCE and RECENT_TRANSCRIPT, and asks for the check of the last line.
  - The `CTX: fact_checker` addendum: check only the facts asserted or endorsed in the last line; use the earlier lines to understand it; do not report facts that appear only in earlier lines. It includes the made-up concentrate example (90 mL of water, not 90 mg of caffeine).
  - Same schema, no hold. The compliance and context judges are unchanged under this switch.
- **Tests:** `tests/test_d334.py` (the pair judged once by each judge, a lone question judged alone after the hold, the CONVERSATION block).

D-335: QUESTION_HOLD's model trigger, marked pairs and the operator's chip (user-approved 10/8 after the D-334 result: the hold won, CONTEXT_JUDGE dropped; chirp_3 kept "?" on 21 of 24 TTS question lines). Everything stays behind `QUESTION_HOLD`.
- **Model trigger:** under `QUESTION_HOLD` the context judge's output (`ContextOutputQ`) first gives `expects_resolution`. It is true when the line asks something or relays a claim that the next line is expected to answer, confirm or reject. That covers questions without "?", particles ("meh", "hor", "right?"), "a viewer says …" and an unfinished question. The `QHOLD: context_judge` addendum carries made-up examples.
- **When it applies:**
  - A line that ends with "?" is held as in D-334.
  - A line without "?" is judged alone as before. If its verdict is `expects_resolution`, the next final, within `QUESTION_HOLD_MS`, is judged as a pair with it through the D-088 merge path.
  - The next final waits at most 300 ms for that verdict; a later verdict gives no pair.
  - Alerts already raised from the first line are not raised again: the merge protects the chain's notes, and compliance skips a rule already active on the chain (tested).
- **Marked pairs:** a pair reads "[previous line] …" then "[this line] …" on two lines for all three judges. The fact checker reads it as one UTTERANCE, not "A / B". `PAIR` addenda for the compliance judge and the fact checker, and the same sentence in the context judge's: judge what [this line] asserts, endorses or rejects about [previous line].
- **Operator only:** `hold.started` / `hold.ended` events. While a "?" question waits, the operator header shows "맥락 확인 중 · 최대 2.5초" ("Collecting context · up to 2.5 s"). The host screen shows nothing.
- **Logs:** "pair <t1> + <t2> trigger=?|model|both after N ms: judged as one". Eval rows keep `ms_from_first_final` (D-334).
- **Tests:**
  - `tests/test_d335.py`: a paired line, no pair when the verdict is false, no pair when the verdict is late, no repeated compliance alert, the operator hold events.
  - `tests/test_d334.py` (marked pair).
  - `src/app/state.test.ts` (events).

D-336 (review-1008 H6): the code defaults are now the measured config, and `deploy/cloudrun.sh` states it explicitly. Before, the code defaulted to the verifier arm and v1, and the cloud took whatever the code said.
- **New defaults:**
  - `JUDGE_ARM=single`, `SINGLE_MODEL=gemini-3.5-flash-lite`, `SINGLE_THINKING=MEDIUM` (compliance), `SINGLE_FACTS_THINKING=LOW`.
  - `FACT_PROMPT=v5`, `JUDGE_SEED=7`, `STT_ENDPOINTING=STANDARD`.
  - `QUESTION_HOLD` stays off until the qh2 run.
  - `.env.example` matches.
- **Deploy:** the script's `--set-env-vars` lists the same values, `QUESTION_HOLD=false` included. Nothing is deployed until the user deploys.
- **Tests:** the older tests keep the paths they were written for (the conftest pins the previous values). The verifier-arm tests use `VERIFY_SHIPPED`, the config as shipped from D-305 to D-335. `tests/test_d336.py` checks the defaults and the deploy script.

D-337 (review-1008 A2, A3, E6): no 404/500 buttons and no raw server or infra strings on screen.
- **"New demo session"** (the Hub and the demo console) now asks for `POST /api/demo/sessions`, the demo show. The empty `POST /api/sessions` answered 404 `unknown_runsheet`, because there is no shipped run-sheet.
- **Demo feed:** a show with no demo chatter (a release show) no longer starts it; `start_pool` raised `KeyError 'min_gap_ms'`, a 500. The feed state carries `pool_available`. The console hides the chatter buttons and every burst button the show does not have, and says "No demo feed for this show."
- **Errors:** screens show `userMessage(e)` instead of the server's text: Hub, demo console, test drive, summary, and the app's session lookup. It is a short neutral line, in Korean too: can't reach the server, the show is no longer available, the test drive is busy, demo tools are off, something went wrong. The onboarding screens are someone else's and were not changed.
- **Infra strings removed:**
  - "Speech-to-text is off (STT_PROVIDER=mock)" is now "… in this environment" (mic and console).
  - "This show ended (server restarted)." is now "This show is no longer available." (KO "방송 연결이 끊겼습니다.").
  - "Google shared capacity busy" is now "AI service busy" (KO "AI 서버 혼잡").
- **Tests:** `tests/test_d337.py`, `src/screens/screens.test.tsx` (the Hub's demo session; no feed buttons on a release show), and the updated strings.

D-338 (review-1008 H3/H4, provenance only): in the single and verifier arms, `hard_validate` (`verify=True`) returned before its approved-claims check. A fact contradiction could cite the "Approved on-air claims" section, which holds the approved and the not-approved claim lists, and the host then got a fact note quoting the not-approved list. The verify branch now drops such a claim and logs "provenance: an approved-claims passage (claim wording is compliance's)". Claim wording stays with the compliance judge.
- **Test (`tests/test_d338.py`):** the host says a not-approved phrase of the demo-fixture cream. The result is one compliance alert, no fact note, and the drop in the log. The test fails without the fix.

D-339 (review-1008 H13/H14, with the planner's correction and addendum): a speech-stream watchdog, timing logs, and the mic stream closed at show end.
- **Trigger:** chirp_3 sends no interim results, and STANDARD endpointing waits through continuous speech, so "no result for 8-10 s" would misfire. The trigger instead uses the existing speech-energy check. If the live stream heard speech after its last final, then a pause, and no final came within `STALL_MS` (5 s) of that pause, it is restarted. Before its first result the limit is `COLD_STALL_MS` (8 s), and speech within 1 s of the last final counts as that final's tail.
- **Restart:** the restart re-sends up to `BRIDGE_STALL_MS` (20 s) of unfinalized audio, up from 5 s, so the speech is not dropped. The mic is told "reconnecting" (chip: "Reconnecting…") and "listening" again at the new stream's first result.
- **No restart loops:**
  - A stream opened by a stall restart is not stall-restarted again until it returns a result.
  - If the mic's own audio is late, a restart would not help, so there is no restart: the stall is logged and the chip shows once. The mic sends a capture-time mark about once a second; the smallest server-minus-client gap is the baseline, more than 2 s over it counts as late, and over 1 s is logged.
- **The 36 s gap of review §4.3 was a delayed burst, not silence.**
  - Each final now logs its timing: audio end offset, server receipt, sent to Google (with the queue lag), and final arrival (Google's time).
  - Each stream ("lane") logs on its end: bytes in, audio seconds, results, last response, and why it ended (switch, limit, stall, error, closed).
- **Not twice:** a final whose speech end is not after the latest reported one is dropped and logged. This covers late finals of a replaced stream and finals of re-sent audio.
- **Show end (H14):** an open mic checks the show once a second. When the show ends, it sends "The show ended." and closes with code 4410, which the mic does not retry; the speech stream closes with it.
- **Tests (`tests/test_d339.py`):** a stream that stops answering is restarted and its speech re-heard; a late but working stream is not restarted; a cold-start stall restarts once, with no loop; the old stream's late burst after a restart is reported once (this test fails without the drop); late mic audio shows the chip with no restart; the stream closes at show end.

D-340 (review-1008 H15, and the H19 note):
- **429 retry:** `LLM_RETRY_ON_429_MS`, 0 by default, so no change until measured. When it is set, a 429 (Google's shared capacity) is retried once after that wait, but only if at least 1 s of the call's deadline remains after the wait. A second 429 is not retried. Compliance and number facts keep their own once-more retries. Tests: `tests/test_d340.py`.
- **H19 (risk noted only, no change until the qh2 results):** the question hold (D-334/D-335) joins the next final to a held question without checking that the next final answers it. A held question followed by an unrelated new sentence, inside `QUESTION_HOLD_MS`, is judged as a pair. The marked lines and the PAIR prompt sentence ("judge what [this line] … about [previous line]") leave the meaning to the models, but the pairing itself is unconditional.

D-341 (review-1008 H16-H18):
- **H16:** a qualifier add-on ("That's from our in-house test.") fixes a TEST-QUALIFIER alert only within 10 s (`LATE_QUALIFIER_MS`). After that, the host's banner title changes from "ADD 'IN OUR IN-HOUSE TEST'" to "SAY THE RESULT AGAIN WITH 'IN OUR IN-HOUSE TEST'". The Korean title keeps the English phrase the host must say ("'in our in-house test' 붙이기", E2).
- **H17/H18:** the context verdict of every line is logged at INFO: type, matched answer, covered points and cues, transition, quote, target, confidence, and `expects_resolution` under the question hold. So is every switch decision: on-air and next product, the kind, the state and the cue count. With these, a switch that did not happen (review U3) can be traced. The switch rule itself is unchanged.
- **Tests:** `src/screens/host/host.test.tsx` (the late title) and `tests/test_d341.py` (the logs).

D-342 (review-1008 H20): a sentence with an active HIGH compliance alert shows only that alert on the host screen. Its MEDIUM banners and its fact notes stay in the alert log and the operator's views, but are not stacked on the host's card. Other sentences keep theirs. Display only: alerts, logs and eval rows are unchanged. Test: `src/app/selectors.test.ts`.

D-343 (logic freeze, user 10/8): `QUESTION_HOLD=true` is now the code default and is set in `deploy/cloudrun.sh`. Measured on pool 7 plus the paired set: two-host lines went from 82.8% to 96.6%, with no one-host regression. STT_DUAL is cancelled. From here, no changes to the judges, prompts or STT logic.
- **Tests:** the older tests pin `QUESTION_HOLD=false` through the conftest pins and `VERIFY_SHIPPED`. `tests/test_d336.py` checks the new default.

D-344 (review-1008 E4/E5, wording only): display text from the review, small and display-only under the logic freeze. Korean is updated with each key.
- Hub: "…chat with fact-checked AI answers."
- Operator question desk: "Grouped by topic."
- Host:
  - "Questions resume after the correction" (was "Finish the correction first")
  - "AI check is slow. Some alerts may be late or skipped."
- Test drive: "Loading the saved reading…"
- Summary: "Host said".
- Viewer correction notice for non-price fields: "Correction: the {field_label} of {product_name} is {correct_value}." The old template read "Correction: Hydra Barrier Cream volume is 50 ml."
- Not done: E1's 제품/상품 unification and the per-screen Korean keys. They touch many keys across screens and are left for after the freeze.

D-345: `FACT_PROMPT=v7` (`prompts/fact_relation_v7.md`), a new arm. The default stays v5 until it is measured; user-approved 10/8 as the last change before the freeze, reviewed by GPT, Gemini and Sonnet.
- **New field:** v7 is v5 plus `stated_as_heard` in the schema (`FactRelationOutputV7`), between `source_value` and `relation`. It is the stated value re-read with speech-to-text's number-word homophones as digits ("for"/"four" is 4, "to"/"too"/"two" is 2, "ate"/"eight" is 8). The order and place value of every digit are kept. Digits are never rearranged, dropped or computed to make a match. With no such word next to the number, it equals `stated_value`.
- **Rule:** if `stated_value` differs from `source_value` but `stated_as_heard` equals it, the relation is `uncertain` (no alert). If both differ, it is `contradicts`, as before.
- **Examples (made up):** uncertain: "for 0.5 g" for 4.5 g, "20 for dollars" for $24, "1 ate 0 ml" for 180 ml. Contradicts: "for 20 dollars" for $24 (read as 420), "30 ate dollars" for $28 (308), "for 5.5 g" for 4.5 g (45.5). v5's examples carry the field too.
- **Tests (`tests/test_d345.py`):** the field order; the rule and examples; v7 through the pipeline on the fictional fixture product (uncertain gives no alert, contradicts gives one); the default is still v5.

D-346 (user-approved change to the frozen logic; reviewed by GPT, Gemini and Sonnet): after the fact checker, code keeps only provenance plumbing.
- **Kept:**
  - the evidence id must exist;
  - the quote is built by code;
  - the catalog product check;
  - D-338 (no fact source in the claim-wording section);
  - the model's own REPORTS_OR_ASKS and `uncertain` handling;
  - `JUDGE_SEED=7`.
- **Log-only now, in the single and verifier arms (`hard_validate` with `verify=True`).** These two checks no longer drop or change a claim:
  - (a) every number of the correction must be in the product's passages or record;
  - (b) without a passage, the correction must be a term of the active promo or offer.
  Each logs "fact claim kept: would drop (log-only): <reason>". It also adds an entry to the eval rows' `dropped`, with that reason and `log_only: true`, so the would-have-fired count can be read from the same rows. The guards arm (`FACT_GUARDS=on`, not shipped) is unchanged.
- **Finding (`tests/test_d346.py`), a made-up product "Velmora Night Balm":** its brochure file and its record both list "NOT APPROVED: Cures eczema.", and the host says "This balm cures eczema overnight."
  - When the fact checker cites the record's not-approved sentence: one compliance alert and no fact alert (D-338). The test passes.
  - When the fact checker cites the brochure file's NOT APPROVED line: a compliance alert and a fact alert. A release file passage ("Source file" section) is a valid fact source, so its not-approved lines are not recognised. Not fixed, as asked. The test is marked `xfail(strict=True)`, so it fails loudly once fixed.
- **Test changed:** `tests/test_verifier.py` (D-300) now expects the "number in no passage" claim to stand.

D-347: `FACT_PROMPT=v8` (`prompts/fact_relation_v8.md`), a new arm from the D-346 finding (option 2, a prompt change, no code check; user-approved, chosen by GPT, Gemini and Sonnet). The default stays v5.
- **v8 = v5 plus one rule:** a list of claim wordings that the brand or a regulator rejects is never a fact source and is never cited as evidence. Such lists look like "NOT APPROVED: …", "Claims not approved", "Do not say …", "Avoid saying …", a banned-wording table row, or the same in another language. A real usage caution ("Not approved for children under 4 months", "Do not use on broken skin") stays a fact. Made-up examples Q-S.
- **Kill rule, set before the probe:** v8 is dropped if any must-alert case is lost, or if any fact alert still cites a banned line.
- **Real-model probe (`scripts/probe_banned_lists.py`, Flash-Lite LOW, seed 7, one call per case):** the made-up release "Velmora Night Balm" has a brochure with every list form; the host lines are written as live speech.

| Host line | v5 | v8 |
|---|---|---|
| "This balm clears up eczema overnight, guys." (record + file list) | no alert (D-338 drop) | no alert |
| "Honestly, it gets rid of your wrinkles for good, you'll see." (table row) | fact alert citing the banned row | no alert |
| "Your pimples will be gone in just one day, trust me." (Malay list) | fact alert citing the banned line | no alert |
| "Scars heal in three days with this, seriously." ("Do not say:" line) | fact alert citing the banned line | **fact alert citing the banned line** |
| "You get a nice big 50 ml jar." (true fact) | no alert | no alert |
| "And you get a 30 ml jar, so it lasts a while." (wrong fact, must alert) | alert | alert |
| "Even your two-year-old can use it, no problem at all." (real caution reversed, must alert) | alert | alert |

- **Result: the kill rule fires.** v8 removes three of the four banned-line alerts and keeps both must-alert cases, but the "Do not say" line is still cited in one case. An earlier probe line ("It heals scars in three days.") was not cited under v8, so it depends on the line. The decision is the planner's and the user's.
- **`tests/test_d346.py` is unchanged:** a scripted model cannot show what the prompt does, so the xfail stays. The real-model probe above is the evidence. `tests/test_d347.py` checks v8's rule, examples and wiring.

D-348: UI fixes from the user and the UI QA of cloud revision 00006 (display only; no judge, switch or STT change).

- **Covered points and ingredient numbers stand out instead of fading.** A said point keeps the check icon; its text now sits on a highlighter background (`--said-bg`: light green #d6f0c2, dark #2c4a26) and stays in the full text color. A said ingredient gets the same highlight on its name plus a check, so the state never depends on color alone. Points not yet said are unchanged.
- **No "Avoid saying" heading over an empty list.** The block is left out when the product has no wording to avoid.
- **The operator chip says what it counts.** "Risky lines alerted 1/6" divided by every final line (switch and correction lines too), so it read as "missed 5 of 6". It is now "Lines with alerts 1 / 6 lines" (Korean: "알림이 뜬 줄 1 / 전체 6줄"). The backend count is unchanged.
- **The demo console no longer squeezes the prompter.** A height dragged earlier (remembered per browser) could reach 85% of the window and leave the panes about 0 px. The drag now stops at 46% of the window, the same cap as the CSS, and the inline style no longer lifts that cap. Probe at 1440x900 with a remembered 700 px: before, the prompter's points had 0 px visible; after, the console is 414 px and the points keep 315 px.
- **A rule source that names several files puts the alert product's file first.** "Cream.pdf Page 2 §7; Ampoule.pdf Page 2" on an ampoule alert now reads "Ampoule.pdf Page 2; Cream.pdf Page 2 §7". The file-to-product map comes from the catalog passages (`doc`, `product_id`). Both files stay listed, because code cannot tell whether they say the same rule.
- **The mic-language select offers only Session default, English (en-US) and Korean (ko-KR), to everyone.** The Korean suffix "· 실험 중 · 정확도 미측정" is gone, and so is the labs gating (`?labs=1`, `isLabs`, `MEASURED_LANGUAGES`, `micLanguages`). The other nine languages and "auto" are no longer listed; a stored pick of one of them falls back to Session default.
- Tests: `host.test.tsx` (said point: class, check, whole text; open point: no check; ingredient check; no empty avoid heading), `ui_qa.test.tsx` (chip wording, file order), `screens.test.tsx` (a remembered 5000 px console is capped at 46%), `prefs.test.ts` (two languages, no labs, unlisted picks dropped).

D-349: `SWITCH_MODE=immediate`, a new switch arm (user-approved; chosen by GPT and Sonnet, Gemini differed). The default stays `two_step` (D-090 arm-and-confirm) until the arms are measured. Settings: `SWITCH_MODE` (`two_step` | `immediate`) and `SWITCH_DUAL_SCOPE_SEC` (10; the user set 10 s, not 30 s).

- **Decision:** in `immediate`, the context judge's transition verdict alone switches the prompter, at once. The verdict must be a transition to the next product, with medium or high confidence, and not a quote or an answer. There is no name match (`SWITCH_ARM_NAME` is ignored), no confirming line, no 5 s pending and no HIGH-alert gate. Every transition verdict is logged ("switch decision ... reason=...") and emitted as `segment.switch_decided` with the transcript id, the target, the confidence and the judge's reason. The operator's manual switch and the 60 s undo are unchanged.
- **Host:** there is one prompter (the new product) and no preview card. A bar "Switched to <product> · Undo (Esc)" shows for 8 s after an immediate switch. Undo calls the existing `/segments/undo`. A two-step or operator switch shows no bar.
- **Judge scope after a switch or an undo:** for `SWITCH_DUAL_SCOPE_SEC`, the fact checker and the compliance judge get both products. This is a model scope, not a code gate.
  - The fact checker gets the previous product's passages and file text. `SWITCH_CONTEXT.previous_product` labels that product ("was on air until a few seconds ago; the current product is now on air"). Its claims already name a product, and that product's checks apply (provenance only).
  - The compliance judge gets a `PREVIOUS_PRODUCT` block (its name, its approved claims and the instruction) and its rules. Only for those lines, the output schema adds `product_id` per violation (`with_product`), so the model says which product each claim is about.
  - Code keeps a pick only if it is one of the two products; anything else becomes the on-air product. say_instead comes from the picked product's approved wording (`approved_say` / `negated_caution` on that product), and the alert carries that product.
  - Outside the window, the prompts and schemas are exactly the default ones.
- **No handling of back-references** (user, 10/8: the host does not go back to the previous product).
- **Eval tool `scripts/eval_switch.py` (now `scripts/eval_show.py`, below):** replays one show's ordered lines with their real gaps through ONE sequential multi-release session (`release_ids`). Input is a JSONL of `{show_id, release_ids, lines:[{id, text, gap_ms, expect: "stay" | "switch_to:<n>"}]}`.
  - Flags: `--mode two_step|immediate`, and `--arm-name on|off` for two-step.
  - Output (`<out>.json` and `.md`): every line with its transcript id and time; every switch event in order (decided, counting, pending, cancelled, committed, undone) with its time and transcript id; every alert with its release and `ms_to_shown`.
  - Score: a caught switch is a commit to the expected product between its line and the next expected line, with latency = commit time minus the line's final. Any other commit is a false switch.
- Tests: `tests/test_d349.py` (switch at once; no switch on a quote, an answer, low confidence or another target; default unchanged; both products in scope inside the window only; the alert and its wording follow the picked product, and a pick outside the scope falls back to the on-air product; an undo opens the window; the eval tool on a made-up two-release show), plus frontend tests (the Undo bar, Esc, no preview card, no bar after a two-step commit, the event reducer).

D-349 (follow-up): `scripts/eval_switch.py` becomes `scripts/eval_show.py`, a general show replay. The user wants every live feature measured, not only alert accuracy. It is an eval script only; there is no app change.

- **Input:** the same format as before, plus optional per-line `labels`, which are copied to the output untouched.
- **Run:** one sequential session per show, with real gaps.
- **Output:** `<out>/<show_id>.json` per show and `<out>/summary.md`. Times are on the session clock, and each `ms_*` is from the line's final. The JSON has these parts:
  - `lines`: each line with its transcript id and line end, the release on air, the context judge's verdict (covered_point_ids, covered_cue_ids, switch verdict, reason) and its model calls (status, failure, latency, usage).
  - `switch_events`: decided (with the judge's reason and confidence), counting, pending, cancelled, committed and undone.
  - `alerts`: kind, rule or field, severity, the release it was checked against, then the provisional reflex chip, shown, escalated and resolved times, and the line that corrected it. For the qualifier rule, it also records whether the banner was shown, when the 10 s re-say prompt appeared and whether the alert was cleared.
  - `prompter`: each coverage update with the required points left, attributed to the line said just before.
  - `chips`: question holds, "checking" (verify.started/done), and provisional chips that never became an alert.
  - `judge`: failures and health changes.
  - `calls`: every model call with its usage.
  - `timeline`: the raw live events in order.
  - `switch_score`.

D-350: white screens in demos (user report). The frontend had no React error boundary, so a render exception unmounted the whole app. This is a display and robustness change only; there is no judge, switch or STT change.

- **Error boundaries (`PanelBoundary`):** there is one at the app root and one around each Studio pane (host, operator, viewer) and around the demo console.
  - On an error, the other panels keep running, and the broken one shows a small card: "This panel hit an error · Reload panel" (KO: "이 패널에 오류가 났습니다 · 패널 다시 불러오기"). Reload remounts the panel, so its state comes fresh from the server.
  - The error goes to `console.error("[panel-error]", panel, message, {stack, componentStack, lastEventType})`. There is no client-log endpoint, and adding one would be a backend change.
  - `lastEventType()` in `sse.ts` is the type of the last live event received.
- **Event guard:** `reduceEvent` now catches an exception while applying one event. A payload this client cannot apply would otherwise throw inside every screen's state update at once. The event is skipped and logged (`[live] event skipped <type>`), its seq still advances, and later events apply.
- **Likely crash:** the screens were fed the suspects named in the report:
  - null say_instead, span, rule, severity, field and values
  - an unknown alert kind
  - a product missing from the catalog after a switch (the on-air segment's product not in the catalog)
  - an empty prompter
  - an unknown event type, and `segment.switch_decided`

  Host, operator and viewer all rendered without a crash, so no single render bug reproduced. The one reproducible way to crash is an event whose payload a reducer branch cannot read (for example `segment.extended` with no segment): that throws inside the state update of every screen at once, which matches "the whole screen goes white". The event guard covers it, and the boundaries cover any render error not found yet. `checked_against` is a field of `eval_show.py`'s output, not of the app.
- **TEST-QUALIFIER say_instead:** a test result's wording is "<result>, <test conditions> (<qualifier>)". The format is built by the onboarding release (not this team's code), and the conditions can be a long passage.
  - Neither the demo releases nor our PDF text extraction contain U+FFFD; the demo PDFs' "30°C" extracts cleanly. So the broken "22 ± 2 °C" text comes from a non-demo release's record (onboarding) or from the console the replay was read in. It is not fixed at the source here.
  - The host overlay, the MEDIUM banner and the operator card now show `shortSay(...)`. A line longer than 120 characters, or one holding U+FFFD, loses its test conditions but keeps the result and its qualifier. The operator card keeps the full text as a tooltip.
- Tests: `src/screens/robust.test.tsx`: an unknown event; an event that cannot be applied is skipped and later events apply; host, operator and viewer render the odd data without the error card; a throwing panel shows the card, its sibling stays, the error is reported, and Reload brings it back; shortSay cases.

D-351: the user's switch rule for `SWITCH_MODE=immediate`, after a review by GPT, Gemini and Sonnet. The rule stays as the user gave it. Also: the 429 retry is on.

- **The rule:** the run-sheet order is fixed, and the target is always and only the next product.
  - The switch happens when the host says they are moving on now AND names that next product: its name, its short name, or its type word without the brand ("next up, the serum").
  - Naming any other product does not switch: the product after next, a later product of the same type.
  - There is no catch-up and no "switch to X?" chip. The operator's manual switch covers a missed switch (user's rule).
- **Who decides:** the context judge, not a code string match.
  - In this arm its switch verdict has one decision field, `moving_to_next_named`, written before `target_product_id`.
  - Code checks only that the line is not a quote and that the target is the next product. There is no confidence threshold, and a line that answers a viewer and then moves on can switch (the answer gate of D-349 is gone in this arm).
  - Every transition verdict is logged and emitted as `segment.switch_decided`, now with `named`.
- **Run sheet for the context judge:** each product's name, short name, type word (`generic_word`, read from its approved release record) and status (done, on_air, next, later).
- **Prompt:** a system addendum, `design_arms.md` "SWITCH: context_judge", with fictional examples only. It also covers:
  - an answer followed by a move;
  - a move split over two finals: the last line of RECENT_TRANSCRIPT plus UTTERANCE, counted on the second line only and never from an older line;
  - plans ("the serum is coming later"), comparisons and quotes, which are not moves.
- **Late verdicts:** a verdict on a line said before a switch or an undo is dropped by its segment generation, so a switch is never applied twice. A test covers an Undo followed by a late verdict.
- **Context retry:** in this arm, a failed context call (timeout, error, invalid, or a 429) is made once more.
  - Both calls share `CONTEXT_RETRY_TOTAL_MS`=4000 from the first call's start. The retry runs only with at least 1 s left, and each call is capped at `JUDGE_TIMEOUT_MS` (2.5 s).
  - These calls skip the LLM layer's own 429 wait (`LLMRequest.retry_429=False`), so the two retries never stack.
  - Worst case: the switch verdict comes 1.5 s later than without the retry.
- **429 retry on (user-approved):** `LLM_RETRY_ON_429_MS`=500 is the code default and is set in `deploy/cloudrun.sh`. A 429 is retried once after 500 ms, only when the deadline still leaves 1 s (D-340). For a 2.5 s context call that answers a 429 within about 1 s, the retry fits. A 5 s compliance or fact call always fits.
- Tests (`tests/test_d351.py`, made-up three-product shows):
  - the run sheet carries short names and type words;
  - a name, a type word only, and an answer followed by a move all switch;
  - a split move switches on its second line;
  - two serums: only the next one switches;
  - no switch for a plan, a comparison, a move with nothing named, the product after next, or a quote;
  - a late verdict after an Undo is never applied;
  - a failed context call is made once more, without the 429 wait, inside the deadline.

  The D-349 test that blocked an answer line and a low confidence is narrowed to quotes and other targets.

D-352: a correction, or a qualifier said again, that comes before its alert turns active is no longer lost (the normal-flow replay: "This toner cures eczema..." then about 2 s later "Sorry guys, I shouldn't have said it cures eczema."; the apology was judged while the alert was still provisional, so the HIGH stayed and escalated; 1 of 3 corrections and 4 of 6 qualifier re-says cleared). Reviewed by GPT, Gemini and Sonnet. Compliance verdicts apply as soon as they arrive, so a later line's verdict can come first.
- **Listed while provisional:** when the compliance judge lists, in `corrects_alert_ids`, an alert that is still provisional (it was in ACTIVE_ALERTS as a reflex chip), the correction is stored. It applies the moment that alert turns active, before its escalation (the escalation timer is cancelled). `apply_corrections` itself still only handles active alerts.
- **Judged before the alert existed:** when an alert turns active (a compliance alert or a TEST-QUALIFIER banner), the later lines of the same segment whose compliance verdict was already applied are asked once each. That is at most 2 lines, within 10 s of the alert's line. The compliance judge gets the line, the alert's line as RECENT_TRANSCRIPT and this alert alone in ACTIVE_ALERTS, and it corrects the alert only if it lists it. A failed or timed-out call is never a correction.
- **Log per correction:** `correction <sid> t=<line>: alert=<id> in_active_alerts=<bool> listed=<bool> -> applied | waits for its alert to turn active | not listed | not an alert of an earlier line`, and `correction <sid> re-check: alert=<id> t=<line> status=<call status> listed=<bool>`.
- This works with `CORRECTION_CHECK=judge`, which is the default from D-353. Provenance only: the listed id must be an alert the judge was shown. There is no word check: the arm-A correction schema carries no quote to check against the line.
- Tests (`tests/test_d352.py`): a provisional alert corrected while provisional turns active as corrected, without a second call; a line judged before the alert existed is asked again and corrects it; a failed re-check leaves the alert active.

D-353 (user order 10/8, top priority): no code check that matches words, names, numbers or regexes against the host's speech text on the live path. The model's alternative is now the default, and the D-308 "back until measured" defaults are overruled by the user. Each setting is also in `deploy/cloudrun.sh`, except FACT_FIXES: `--set-env-vars` splits values on commas, so the code default applies. The live path was audited end to end: STT final, hold and merge, judges, validation, alerts, corrections, escalation, qualifier banner, prompter coverage and switch.

| Setting or function | What the code did | New state |
|---|---|---|
| `CORRECTION_CHECK` words → judge | `check_correction` (word coverage, numbers, negation plus 50% of the span), `says_the_replacement` (D-098), and `_reconcile_late_alert` corrected or vetoed corrections | the compliance judge's listed alert ids only (provenance: an alert it was shown); D-352 handles the timing |
| `SWITCH_ARM_NAME` True → False | a code name match on the line was needed to arm a two-step switch | the model's target alone (two-step); the immediate arm (D-351) was already model-only |
| `VERBAL_CHECK` code → judge | regexes for hedges and parsed numbers decided whether a spoken answer posts, and which draft it answers (`verbal_check`, `relink_candidate`) | the context judge's fields (arm B's) |
| `JUDGE_PRODUCTS` named → all | an alias match on the line picked which products' rules and fact passages the judges got, and filtered reflex hits | every show product; the model says which one a claim is about |
| `REFLEX_SCAN` True → False | the regex pre-scan chip, with negation and quote word cues | off; a line whose judge call fails gets the neutral "check this line" card (`REFLEX_ON_FAIL=card`, no regex) |
| `QUALIFIER_ADDON` True → False | a regex found an "in our in-house test" add-on that corrected or dropped qualifier alerts (D-151/155) | off; the compliance judge corrects (D-352 covers a re-say that comes early) |
| `FACT_FIXES` all → `F1,F5,Q6` | Q5 held a fragment ending in a word from a list or a bare number; Q1T made a code-added TEST-QUALIFIER alert from regexes, number matching and tester-name regexes (with G4 and G5); Q2, G1 and the other letters are code checks of the guards arm | only the fixes that are prompt lines (`design_arms.md` F1, F5, Q6). The code parts of F1 and Q6 run only in the guards arm and in `post_validate`, both off. Tests of the code checks name `ALL_FIXES` |
| `validate_compliance` D-252 `lex.affirms` | affirmation words on the line turned a quoted violation into the host's own claim | the guards arm only; the model's `is_quoted` stands |
| TEST-QUALIFIER `qualifier.approved_replacement` on the line | the numbers and words of the line chose which recorded result the say_instead uses | the guards arm only; the model's `qualified_result_id` names it, otherwise `approved_say` on its say_instead |
| `negated_caution` | negation words plus caution word coverage on the line chose the say_instead | the guards arm only |
| `NUMBER_CHECK`, `FACT_GUARDS`, the D-346 log-only checks | (unchanged) | off, off, log-only |

Kept (the user-approved plumbing): the evidence id exists, the code-built quote, a known product id, D-338, scheduling and timing, the seed, retries. Not changed in this batch, listed for the user's call:
- `ends_sentence` (D-088 merge) and `asks` (D-334 question hold) read STT punctuation (". ? !"), not words.
- `approved_say` and `qualified_say` map the model's say_instead (model text, not STT) onto approved wording by word coverage. Turning them off would show the model's own sentence to the host. The model alternative needs an approved-claim id in the schema, which is a new field.
- `qualifier.is_repeat`: string equality of say_instead to avoid a second card for the same result.
- `facts._corrected_note`: number equality of the model's stated and correct values to close a promo note.
- `utterances._run_facts`: the fact check is retried only for a line with a spoken number (a retry condition).
- `publish.states_number` and the rest of the spoken-answer posting belong to the comments team (out of scope).
- Tests: `test_d305` (no regex chip by default); `test_d298`, `test_d299` and `test_relation` now name `ALL_FIXES` for the opt-in code checks they test.

D-353 addendum (user order, 10/8): `VERBAL_CHECK` goes back to `code`. Spoken-answer posting belongs to the comments team, so it is outside this team's scope. The code default is back, `VERBAL_CHECK=judge` is removed from `deploy/cloudrun.sh`, and `.env.example` matches. No test had been changed for it. The D-353 table row for VERBAL_CHECK no longer holds.

D-354: `STORE=firestore` stores the live show data in Firestore. The database is `live-studio` (setting `FIRESTORE_DATABASE`) in project ai-budiler-cup-uh-team-pjt, created by the user. The design follows 2 of 3 peer reviews (GPT, Gemini, Sonnet). The default stays `STORE=memory`, and tests use MemoryStore.
- **Memory stays the read model.** `FirestoreStore` extends `MemoryStore`: every get and query is served from memory, so the alert hot path never waits on Firestore. That matters because `bus.emit` awaits `store.put` under the session lock.
- **Write-behind:** every put, delete and committed transaction write is mirrored to Firestore through one ordered queue.
  - Writes to the same document are coalesced (the latest wins), and they go out with `set()` (whole documents, no dotted updates) in batches of at most 500.
  - The queue is flushed when a show ends (`end()` waits up to 10 s) and at app shutdown (SIGTERM: the lifespan's `aclose` waits up to 8 s, inside Cloud Run's 10 s).
- **Failures:**
  - A transient failure keeps the whole batch queued and retries it with backoff (0.5 s, doubling, up to 30 s), logged as `firestore: write failed`.
  - A document Firestore refuses (InvalidArgument, FailedPrecondition or BadRequest) is retried alone, then as one JSON string field; if it is still refused it is logged as an error.
  - A document over the 1 MiB limit is logged as an error and not written (`failures` counts these).
  - Nothing is dropped silently.
- **Read-back:** the first time a process touches a session, it reads back the session document and its subcollections, so the event seq continues on a new instance. A document already in memory or in the queue is never overwritten by the read-back.
  - Other top-level collections load whole on first touch. A listing of `sessions` loads only the session documents.
  - A failed read-back is logged, and memory serves alone for 30 s before the next try.
- **Documents:**
  - Paths are `sessions/{sid}/<collection>`, and a doc id with "/" is refused.
  - A document holding an array inside an array (Firestore has none) is written as one `_json` string field and decoded on read-back.
  - `delete_session` drops the session's queued writes and then calls `recursive_delete`.
  - No composite index is needed: the queries run on memory.
- **Deploy:** max-instances stays 1, and `STORE=firestore` goes into `deploy/cloudrun.sh` only when the user says so. IAM is the user's job: `roles/datastore.user` for the run service account. New dependency: `google-cloud-firestore`.
- **Tests (`tests/test_d354.py`, on an in-process stand-in of the Firestore client in `tests/fake_firestore.py`):**
  - the store contract of `test_store`, with Firestore equal to memory after a flush;
  - the write path makes no network read, coalesces writes and keeps batches at 500 or fewer;
  - an outage is retried with nothing lost;
  - a refused document neither blocks the others nor is lost;
  - nested arrays round-trip as JSON;
  - "/" in a doc id is refused;
  - a document over 1 MiB is logged and not written;
  - a show replayed through the real pipeline has the same documents per collection in Firestore as in memory, and a new store on the same database reads the session back and continues the event seq;
  - `delete_session` deletes it in Firestore too.

  The same contract runs on the Firestore emulator when `FIRESTORE_EMULATOR_HOST` is set. This laptop has no Java and no emulator, so those 4 tests were skipped here.

D-355: a qualified re-say should clear the TEST-QUALIFIER banner. Reviewed by GPT, Gemini and Sonnet.
- **Evidence:** in a logged replay the re-say line had the banner in ACTIVE_ALERTS, but the compliance judge did not list it, in the line's own call or in the D-352 re-check. The correction job of `compliance_judge.md` (Job 2, Example C) covers only retractions.
- **Prompt arm `COMPLIANCE_RESAY`** (off until measured): the system addendum `design_arms.md` "RESAY: compliance_judge", with fictional examples only.
  - It says to judge a correction by its meaning in context, never by its phrasing. An alert's say_instead is only a suggestion (user, 10/8).
  - For a TEST-QUALIFIER alert, a line corrects it when it states the same test result of the same product (the wording and the number form may differ: "80%" and "8 of 10") and makes clear the result comes from the brand's or the product's own test or a named tester. Any such wording counts, and the words "in-house" are not needed.
  - These do not clear it: a customer opinion; "tests confirm" or "clinically proven" with no source; a different result; the same result with no source; an apology alone.
- **Input (on by default):** `active_alerts_json` keeps the 3 newest alerts plus every active TEST-QUALIFIER banner, so a banner is never dropped from ACTIVE_ALERTS while it is active.
- **Host banner text (display only):** the qualifier banner is now worded as a suggestion, with KO versions:
  - "Say where the result comes from (e.g. 'in our in-house test')"
  - after 10 s, "Say the result again with where it comes from (e.g. 'in our in-house test')"
  - when there is no say_instead, "Say the result with where it comes from (e.g. 'in our in-house test')."
- Tests: `tests/test_d355.py` (the banner stays in the list beyond the newest 3; a corrected banner and other old alerts do not; the addendum is on only with the arm). The host tests use the new wording.

D-354 follow-up (eval tool only): `scripts/eval_show.py` takes `STORE` from the environment when it is set (memory otherwise). Before, it forced memory, so a Firestore run silently used memory. With `STORE=firestore`, the queued writes are flushed (up to 30 s) before the script exits. Each show's JSON `settings` (and the summary header) now holds the effective settings: STORE, FIRESTORE_DATABASE, SWITCH_MODE, SWITCH_ARM_NAME, SWITCH_DUAL_SCOPE_SEC, JUDGE_ARM, JUDGE_MODE, FACT_PROMPT, COMPLIANCE_RESAY, CORRECTION_CHECK, REFLEX_SCAN, JUDGE_PRODUCTS, QUESTION_HOLD and COMPLIANCE_ESCALATE_SEC, read from the context's settings.

D-356 (arm `CORRECTION_HANDLES`, off until measured): the compliance judge saw a correction but returned `corrects_alert_ids: []`. In raw outputs logged before the filter, the reason said "Host explicitly retracts the previous eczema claim." and the list was empty. Reviewed by GPT, Gemini and Sonnet. The change is plumbing and schema only; the meaning rules (D-355 RESAY, meaning not wording) are unchanged.
- **Input:** ACTIVE_ALERTS shows each alert by a per-call handle (A1, A2 ...) with its span, rule, say_instead and status: `provisional`, `active`, or `banner` for TEST-QUALIFIER. The model never sees an alert id. The handle-to-id map stays in that call's values and is never sent.
- **Output:** the schema starts with `alert_checks`, one `{handle, fixed_by_this_line}` per listed alert, before `violations` and `reason`. `correction` leaves the schema the model sees.
  - Code turns each handle marked fixed into its id before the existing id check, adding to any ids a fallback gave.
  - An unknown handle is logged and dropped.
- **Prompt:** the addendum `design_arms.md` "HANDLES: compliance_judge", with a fictional example in which the answer starts with `alert_checks`.
- **Logs:**
  - Per call (the D-352 re-check included, since it uses the same judge): `compliance handles call=<call id> line=... active_alerts=<the block sent> handles=<map> answer=<alert_checks> corrects=<ids>`. The raw parsed answer is also in the call's audit record under the same call id.
  - In every mode, an id dropped by the id check in `validate_compliance` is now logged: `correction ids dropped: not in ACTIVE_ALERTS: [...]`. Before, it was dropped silently.
- **Tests (`tests/test_d356.py`):**
  - the schema starts with the checks and has no correction field;
  - a handle marked fixed corrects its alert, and the request shows handles, no ids and the status;
  - not-fixed and unknown handles correct nothing, and the unknown one is logged;
  - an id the judge was not shown is logged when it is dropped.

D-357: a fix to D-352's spec. The re-check now fires every time a quick correction came before its alert.
- **Diagnostic** (2e25c3b, CORRECTION_HANDLES on, COMPLIANCE_RESAY on, REFLEX_SCAN off): over 3 shows only one re-check was logged. Three quick corrections (two qualified re-says and one apology) were judged before their alert existed, and none got a re-check when the alert turned active.
- **Cause:** D-352 asked only later lines whose own compliance verdict had already been applied. With both calls in flight, that verdict usually comes back after the alert turns active, so the line was skipped. D-352 also required the same segment.
- **Fix:** when any compliance alert turns active (TEST-QUALIFIER banners included), every later line counts as "judged without it" when its judge input was built and did not show this alert, whether or not its verdict is back. That is at most 2 lines, within 10 s of the alert's line, in any segment. The re-check uses the same compliance judge, so it uses the handle format with only that alert when CORRECTION_HANDLES is on.
- **Log:** each trigger decision, `correction <sid> re-check trigger: alert=<id> rule=<rule> t=<line> -> fired | skipped (<why>)`. The reasons are: too late, not judged yet (its judgment will show the alert), already shown the alert, or past the first 2 lines. There is also a line when no later line exists.
- The unused D-352 field `_comp_done` is removed.
- Test: `test_d357_...` in `tests/test_d352.py`: the claim's verdict arrives after the next line was judged, and that line's own verdict comes back even later. The re-check fires, in the handle format, and clears the alert.

D-358 (user order): the live compliance judge reads the regulation ORIGINALS as they are. The rule JSON is gone from its input: no rules block, no bare index, no comparison arms. Its behaviour is fixed in one instruction prompt, and the planner chose option A for the test suite (below).
- **Input:** the originals behind the show's products' rules, as the judge's cached prefix: each file after a "FILE <name>" line, plus a `REGULATION_DOCUMENTS` block naming them. The cache is warmed at session start.
  - For SG cosmetics this is the market source's local file, `data/policy/asean_cosmetic_claims_guideline_appendix_iii_2007.pdf`.
  - A law or brand pack's originals come from its onboarding job's `files.json` (`rule.source_id` -> `lawpacks/<id>.json` or `brandpacks/<id>.json` -> `job_id`).
  - The rule pack is read only to find which documents apply. Onboarding, `sg.json` and the packs are unchanged.
  - A rule source with no original is logged ("compliance originals missing") and marked on each call (`meta.originals_missing`). On the demo this is the product-sheet brand rules, which have no file.
- **Tokens (Vertex count_tokens):**
  - the SG PDF alone is 2,800;
  - the whole cached prefix on the demo show is about 5,194: system instruction 2,177, FILE line plus PDF 2,822, data blocks 195.

  That is above the 4,096 cache minimum.
- **Prompt:** `prompts/compliance_judge.md` is replaced (version compliance_judge_v4). It is now the only compliance instruction, and no addenda apply to it.
  - It flags only a claim the regulation prohibits. A product fact said wrong (dose, size, price, age, usage) is the fact checker's. A documented caution or intended user group said as documented is not a violation.
  - It states the severity criteria. HIGH: disease, cure, safety or guarantee claims, or harm to a vulnerable group. MEDIUM: the rest, such as an unqualified test result.
  - It covers question/answer pairs, split sentences, and corrections by meaning with handles (the D-355 RESAY content). The examples are fictional, in pairs.
- **Output:** `alert_checks` first, then per violation: `citation` ("<document>#<section>" as written in the original, or "TEST-QUALIFIER"), `quote`, `span`, `severity` (the model's), `is_negated`, `is_quoted`, `say_instead`, `qualified_result_id`. The model never writes a rule id.
- **Validation (`validate_original`, provenance only, user-approved):**
  - The cited document must be one the judge was given, and the quote must be in its text (letters and digits compared, so PDF extraction artefacts do not matter).
  - The alert's rule id is the normalised citation (`kelmar-code#2-1`).
  - TEST-QUALIFIER needs a recorded test result, named by `qualified_result_id` or by a quote of its wording. The banner and its corrections key on the alert as before.
  - Anything else is dropped with its reason ("compliance violation dropped by code: provenance: ..."), never silently.
  - `say_instead` stays approved wording: the recorded result's wording for the qualifier, `approved_say` otherwise.
  - The severity is the model's; `alerts.apply_judge_compliance` no longer looks the rule up in the pack.
- **Corrections:** always by handle on this path. `CORRECTION_HANDLES` now defaults to true (and is in `deploy/cloudrun.sh`); it only matters for the legacy path.
- **No production fallback:** the originals path is the code default and has no setting. The old rule-JSON path (`ComplianceJudge` with `prompts/compliance_judge_rules.md`, the old prompt, renamed) is reachable only:
  - through `split_judges.LEGACY_RULES`, which `tests/conftest.py` pins for the existing suite (a test marked `originals` runs the production path);
  - with the mock LLM provider, whose recorded outputs use the old schema.

  It is listed for deletion once the tests are migrated. The old compliance prompt arms (COMPLIANCE_DOCS, ENDORSE, NEG, RESAY, the REL/SINGLE/CONF/V2/FR/Q6/PAIR addenda and DESIGN_ARM E's rule search) do not apply to the originals path.
- `scripts/eval_show.py` records the compliance input in each show's settings: `COMPLIANCE_INPUT`, `COMPLIANCE_ORIGINALS`, `COMPLIANCE_ORIGINALS_MISSING`.
- **Tests (`tests/test_d358.py`, marked `originals`, a fictional "Kelmar supplement code" law pack on a made-up release):**
  - the judge gets the originals and no rules block, and the schema starts with the handles and has a citation but no rule id;
  - a cited verdict becomes an alert named by its citation, with the model's severity and approved wording;
  - a quote missing from the document and an unknown document are each dropped and logged;
  - a correction goes by handle;
  - TEST-QUALIFIER is checked against the recorded results;
  - a rule source with no original is reported.

  `test_prompts` and the D-270 test now read the legacy prompt by its new name.

D-359: a regulation upload UI on the onboarding screen. It is frontend plus ONE read-only backend endpoint; onboarding logic is unchanged (approved by the user, reviewed by GPT, Gemini and Sonnet).
- **`GET /onboarding/regulations`** returns:
  - the approved law packs: pack_id, market, name, regulator, covers, approved_at, the source files (via job_id -> `files.json`), and the sections their rules cite (`file · locator`);
  - `active_for`: the categories each pack is active for (`lawpack_for` takes the newest, so a newer pack replaces an older one);
  - the market's own law and its files;
  - the markets on disk;
  - the categories of the approved releases;
  - per release, the regulation originals its live compliance judge reads (the D-358 lookup on that release's pack), the sources with no original, and `warning` when no law original matches.
- **The "Regulations" panel (`RegulationsPanel.tsx`, below the product onboarding):**
  - upload PDF, HTML or DOCX, with a market pick-list and a category picked from the approved releases' categories (no free text);
  - the job status: queued, reading, done, or failed with its error;
  - the source files and sections of a finished read, then Approve, with the note that approval is write-once and a newer pack replaces an older one;
  - every pack, marked "Active for ..." or "Replaced by a newer pack";
  - the market law;
  - per product, the originals its live judge reads, or a red "No regulation matches this product's category" warning;
  - the note that a read in progress is lost if the server restarts (jobs stay in memory, as before).
- It uses the existing `POST /onboarding/lawpacks/jobs`, `GET /onboarding/jobs/{id}` and `POST .../approve-lawpack`.
- Tests:
  - `frontend/src/screens/onboarding/regulations.test.tsx`: pick-lists; queued, reading and failed statuses; a done read with sections, approval and the write-once note; active and replaced packs; the no-match warning.
  - `backend/tests/test_d359.py`, a mock-LLM flow: upload a fictional law pack, approve it, a matching release lists the original, and a release of another category shows the warning.

D-360: user decisions, reviewed by GPT, Gemini and Sonnet, now the defaults in code and in `deploy/cloudrun.sh`.
- **Compliance thinks LOW:** `SINGLE_THINKING=LOW` (was MEDIUM, D-336).
- **The fact checker flags only facts the host prompter shows:** `FACT_MODE=prompter`, a new mode and the default.
  - Its passages are the prompter's display snapshot (`logic/prompter.py: prompter_passages`), built with the same rules as the host screen's ProductPanel:
    - the price (a time-sale price while a price promo runs, else the live and list price) and the set price;
    - the first 4 ingredient amounts;
    - the points, minus a price point that is not required, under the claims section, so D-338 keeps them out of corrections;
    - the in-house test results;
    - every caution.
  - No product files and no record facts the prompter does not show, such as a size line or the fifth ingredient. The snapshot is both the checker's input and its provenance.
  - In the 10 s dual scope after a switch, the previous product's snapshot is there too. Other show products are not, because they are not on the prompter.
  - The release pack is still built at record level for its other readers (answers to viewers); only the fact checker's input changed.
  - The D-346 log-only checks stay; with no files there is no file route.
  - The snapshot is under the 4,096-token cache minimum, so it goes uncached.
  - `record` and `docs` stay as non-default modes. The older tests are pinned to `docs` in `tests/conftest.py`, and `VERIFY_SHIPPED` keeps the verifier arm as it shipped.
- **Item 3** (extracted text in place of the PDF part) was cancelled by the user. The originals stay as the PDF part (D-358), and the compliance prefix is unchanged at about 5,194 tokens.
- **Originals lookup (the pool-7 HSA pack `law_sg_bb0dff9c_v1` was "missing"):**
  - A lookup that finds nothing is no longer cached, so a pack or file approved or read back later is found on the next call. Before, the lru_cache kept the first miss for the life of the process.
  - Each way the lookup fails is logged with the exact path it tried: no law or brand pack under the root, a pack with no `job_id`, no `<root>/<job_id>/files.json` (local or in the bucket), or a missing file.
  - That pack is not in the cloud bucket (`onboarding/lawpacks/` has no objects) and not in the repo; it lives in the eval VM's onboarding directory, so this session could not verify the load. The likely cause is a pack approved by a script that read the law documents without storing them under its job (`store()` writes `<job_id>/files.json`; `eval_lawpack.py` does not). The next run's log names the missing path.
- Tests (`tests/test_d360.py`): the snapshot is what the prompter shows (no volume line); a price on the prompter said wrongly alerts; a volume that is in the record but not on the prompter, said wrongly, gives no alert; the previous product's snapshot is there in the dual scope; a missing original is looked up again, logged with its path, and found once its files exist. `test_d336` states the new defaults.

D-361: fixes from the codex review (gpt-6-astra high) of 4d4fd9f..5cfe8b2. These are bug fixes and spec fixes, not new features.
- **P1-1, Firestore read-back is all or nothing:** a session's documents are all read first (session, every subcollection), and memory is filled only when every read succeeded. A failed read is tried 3 times, then the call fails loudly. The memory-only fallback is gone: a partial session would restart the event seq at 1 and overwrite stored events.
- **P1-2, a flush wakes a waiting write retry:** a write retry's backoff wait (up to 30 s) is now cut short by `flush()` (show end, SIGTERM), so queued writes go out when Firestore is back inside the 8 s shutdown window.
- **P1-3, no code rewording of say_instead:** `approved_say` (word overlap and numbers) is removed from the originals path. The alert shows the model's own say_instead, which the prompt builds from APPROVED_CLAIMS. A TEST-QUALIFIER alert takes its recorded wording by `qualified_result_id` only (the id is the provenance); the quote-match fallback is gone.
- **P1-4, the quote check keeps letters of any script:** `squash` normalises with NFKC and keeps every Unicode letter and digit (it kept a-z and 0-9 only, so a Korean or Chinese quote became empty).
- **P1-5, the fact checker sees exactly the prompter:**
  - the snapshot has only the first 4 cautions (the rest sit behind "+N more") and no test results (the prompter shows none);
  - in prompter mode the CURRENT_PRODUCT block names the product only, and the promo, offer and set blocks are empty, because their prices are in the snapshot.
- **P2-6, model-listed corrections are not excluded by the merge:** with `CORRECTION_CHECK=judge`, an alert the judge lists is corrected even when the line was merged (D-088) with the alert's own fragment.
- **P2-7, the user's switch rule is the default:** `SWITCH_MODE=immediate` in code, `.env.example` and `deploy/cloudrun.sh`. Older tests are pinned to `two_step`.
- **P2-8, timers are re-armed after a read-back:** a live session that a new process reads back gets its timers again: the tick, each running promo's end, a pending switch's commit, and each HIGH alert's escalation (`SessionRuntime.rearm_timers`).
- **P2-9, two packs with a file of the same name keep both:** originals are found per source, and a name already taken is given as "<source id>:<name>".
- **P2-10, misses are never cached:** the judge's show-level originals are re-read while a source is missing. Found sources are kept per source, so this costs nothing, and a missing source is warned once per process.
- **P2-11, the rule JSON is not reachable in production:** `build_context` refuses `JUDGE_MODE=split` or `single` unless the legacy rules path is allowed (the test pin, or the mock provider).
- Tests: `tests/test_d361.py`, one per fix where it applies; the merge test was checked to fail on the old code. `test_d358` now expects the model's say_instead and qualifier by id only, and `test_d336` states `SWITCH_MODE=immediate`.

D-362: fixes from the codex re-review of D-361 (5cfe8b2..4d4a544), live path only. Codex confirmed D-361 items 1, 2, 3, 4, 7, 9 and 11; these are the rest.
- **A (#5):** the prompter snapshot holds only the set offer the UI shows (the first one containing the product, as in `priceView`).
- **B:** the snapshot holds every caution, because the host can open "+N more" and they are then on the prompter. D-361's first-4 cut is reverted.
- **C (#8):** `rearm_timers` also re-arms each active fact note's hide timer. `schedule_fact_hide` now runs from the note's `shown_at`, so a re-armed timer keeps its time. The comments team's pending-post timer is left alone.
- **D (#10):** a law or brand pack with only some of its files found is not cached: the files found are given, the source is marked missing ("incomplete") and looked up again next time.
- **E:** one originals snapshot per compliance request. `run` takes it once; the prefix the judge gets (`request_documents`), the quote check (`validate`) and the missing-sources marker all use it. A re-read during inference can no longer rename a file or check a quote against another file's text.
- **F:** a fact note is corrected by the model's verdict only: the same cited passage; or, without a passage, the one note whose correct value equals the model's own correct value; or the only note of that field. The numbers parsed from the host's line (`spoken_numbers`) are gone from `logic/facts.py`, and so is its unused `lex` parameter.
- Not changed (the comments team's): `publish.py` spoken-answer posting (an unsure regex, a number compare, word overlap). The planner flags them to the user. #6's remaining case is a non-default DESIGN_ARM path.
- Tests: `tests/test_d362.py` (one set and every caution; a note corrected by the verdict, not by numbers; the fact-note hide timer re-armed at the same time; a partly found pack not kept; the quote check on the request's own snapshot, which fails on the old code). `test_facts` now has the supported claim cite its passage.

D-363: two user decisions after the codex review of D-362.
- **Regulation originals are loaded ONCE per show** (user: "the originals are just put into the prompt"). The judge reads them at show start (the cache warm-up, or the first line) and keeps that snapshot for the whole show; the prefix it gets and the quote check both use it.
  - Never re-read during the show. Removed: the per-call re-read of a missing source (D-361 #10) and the per-request snapshot plumbing (D-362 E). Codex's open point (a failing re-read losing a verdict) goes away with it.
  - A missing original is logged once when the show loads ("compliance originals missing for this show") and stays marked on every call (`meta.originals_missing`). The release screen warns before the show (D-359).
  - Kept: the D-358/D-360 lookup fixes (each failed path logged; a source found incomplete or not at all is never cached for a later show).
- **Fact-note corrections by handle, like compliance alerts (D-356):**
  - Every active fact note goes to the fact checker as an ACTIVE_FACT_NOTES entry with a per-call handle (F1, F2 ...), its product, field, the wrong value stated, the correct value and its status. No real id is sent.
  - The answer then starts with `note_checks`, one `{handle, fixed_by_this_line}` per note (`with_note_checks`, first in the schema). Code maps each handle marked fixed to its id (`FactCheckOutput._corrects`), and `facts.correct_notes` corrects those notes and nothing else.
  - The old matching is gone: by passage, by value, and "the only note of that field" (the regression codex found: a right squalane 3% cleared the panthenol note).
  - The instruction is `design_arms.md` "NOTES: fact_checker" (always on), with a fictional example.
  - **Re-check, as D-357:** when a fact note appears after a later line was already checked without it (at most 2 lines, within 10 s), that line is asked once more with that note alone. Each trigger decision is logged.
  - **Logs:** `fact notes call=<call id> line=... notes=<the block sent> handles=<map> answer=<note_checks> corrects=<ids>`, plus any unknown handles dropped.
  - A line never corrects a note it raised or re-showed.
  - The two mock fixtures of the demo script that correct a note now mark F1 fixed.
- Tests:
  - `tests/test_d363.py`: an active panthenol 5% note plus a right squalane 3% line leaves the note open, and "Sorry, panthenol is five percent" closes it; the request shows handles and no ids; `note_checks` comes first in the schema; a supported claim alone closes nothing; a note that appears after its fix was checked is asked again and closed.
  - `test_d362`: the originals load once and stay fixed for the show.
  - The fact tests script the fix by handle.

D-364: fixes from the codex review of D-363.
- **P1, corrections in line order:** a fact note is closed only by a fix from a line said after the note's latest showing. Sequence: T1 wrong, T2 fix, T3 wrong again, T2's verdict arriving after T3's. T2 no longer closes the note T3 re-showed. The skip is logged.
- **P1, notes the model can tell apart:** each ACTIVE_FACT_NOTES entry also carries `host_said` (the host's words) and `subject` (the source sentence: which ingredient, size or offer). Two notes with the same field and values, one panthenol and one niacinamide, are no longer identical to the model. The NOTES addendum says so. Compliance handles already carry the span.
- **P2, a re-check runs in the line's own context:** each line's fact-check input is kept (pruned with the line's other state), and a late-note re-check sends that same input plus the note. Before, it was rebuilt with the note's product, no previous lines and an empty switch state, so a line about product B after a switch could be re-checked as A.
- Tests: `tests/test_d364.py` (the T1/T2/T3 order, which fails on the old code; two notes told apart by subject; the re-check's request equals the line's own plus the notes block).

D-365: from the codex review of D-364 (P2). When a fact note is shown again with a new value (T1 "ten percent panthenol", then T3 "twenty percent panthenol"), its span is now updated too. Before, the value and line id changed but the span kept the old words, so the model saw `host_said` 10% next to `stated_value` 20%. Test: `test_d365_...` in `tests/test_d364.py` (fails on the old code).

D-366: the planner measured about 29,000 input tokens per fact-checker call on the replay (FACT_MODE=prompter is the code default). Measured on a demo show: in prompter mode the fact checker sends about 17,500 characters (system instruction, prefix and line; about 4-5k tokens) and no files. In docs mode the release's original files are sent too. The repo .env sets FACT_MODE=docs, and Settings reads .env over the code default, so a VM with the same .env runs docs mode. No code change to the mode. Logging only: eval_show writes FACT_MODE and PREFIX_TOKENS (each judge's cached prefix as counted by Vertex) into each show's settings; each call's usage gets `prefix`; the provider logs the prefix count when it counts it; the fact checker logs its FACT_MODE and the number of release files it sends.

D-367 (user): regulation originals are PDF only. The live compliance judge is given only the PDF files of a source (originals._load); any other file (HTML, DOCX, text) is never sent, is logged, and marks its source missing as "<source id> (not a PDF: <names>)", shown in the judge's originals_missing, eval_show settings and the regulations screen. The Regulations panel (D-359) accepts .pdf only and rejects other files with "PDF files only. Not a PDF: ...". The law-pack upload endpoint (onboarding) is unchanged. Tests: tests/test_d367.py, the panel test; the D-358..D-362 originals tests now use real PDFs (tests/helpers.py text_pdf).

D-368 (user): every document upload in the UI accepts PDF only (frontend only; the onboarding backend is unchanged). One check, app/pdfOnly.ts (accept ".pdf,application/pdf"; a pick with any non-PDF is cleared and shows "PDF files only. Not a PDF: <names>"), used by the three file inputs the frontend has: product onboarding (onb-files: Read stays disabled), Regulations (reg-files, D-367) and Setup documents (setup-file-input: nothing is uploaded). There is no drop zone. The test drive ("Try it with a sample product") has no file input: it reads the server's sample documents. Tests: the onboarding, regulations and setup screen tests.

D-369 (user, deploy): Cloud Run runs STORE=firestore with FIRESTORE_DATABASE=live-studio (deploy/cloudrun.sh; the database exists and live-studio-run has roles/datastore.user). max-instances stays 1: a session's timers, SSE and audio WebSocket run in one process. google-cloud-firestore is a main dependency in uv.lock, so the image (uv sync --frozen --no-dev) includes it.

D-371 (user, frontend only): the Setup screen ("Before the show") uploads product and regulation documents in two labelled areas. "Product documents" is the earlier documents table and Upload PDF (product files only). "Regulation documents" is the onboarding Regulations panel (D-359) on the same regulation endpoints (list, law-pack upload, job status, approve), shown without its own heading; it lists only regulation packs and their files. Both are PDF only (D-368). Korean labels for both areas (KO_SETUP), and the Regulations panel now uses t() on the onboarding screen too. No backend change. Tests: setup.test.tsx.

D-372 (user; Sonnet's design): the prompter's "said" ticks for price lines, ingredient amounts and cautions come from the fact checker's verdicts (FACT_MODE=prompter only). Each display-snapshot item's passage id is its item id (`<code>#prompter#<key>`); a running promo's price and set items carry the promo id (`sale-price-<promo>`, `set-<set>-<promo>`), so a tick never carries over to another promo's price. A supported claim (v5: the host asserts or endorses; REPORTS_OR_ASKS never becomes supported) ticks every snapshot item it cites, except points (`point-*`, still the context judge's covered_point_ids). A contradiction ticks nothing; a supported correction ticks its item in the same verdict that closes the note. Ticks go to the cited item's product: its open segment (Segment.ticked_item_ids, saved with the segment, so a Firestore read-back keeps them), its segment that just left the air inside the dual scope, or the next product's pre_covered (split back out when its segment opens, and returned there on an undo). prompter.updated carries ticked_item_ids. The host prompter highlights price lines, ingredients and cautions only by these ids; the ingredient match on covered point text is removed. Kept: the filter that hides a non-required price point from "Points to say" (a display rule the snapshot mirrors, not a highlight). Tests: tests/test_d372.py, host.test.tsx, selectors.test.ts.

D-373: codex review of D-372 (4 x P2). (1) A late-note re-check's supported claims tick too, not only close the note. (2) Ticks come from every supported claim of the line; the D-117 per-subject recency filter is for alerts only, so a right value is ticked even when a later wrong line's verdict arrives first. (3) Ticks are routed by the line's own segment (Transcript.segment_id, captured with the line), not by the scope when the verdict arrives: that segment for its product, and for the product that had just left the air the segment of it before the line's. (4) When the line's segment is gone (an undone switch), the product's open segment gets the tick, else its pre_covered (shown when it goes on air again), never an older segment. Tests: the four D-373 tests in tests/test_d372.py (each fails on D-372).

D-374 (user, 10/9: "판정 결과를 코드가 막거나 버리는 장치 전부 제거, is_quoted/is_negated는 모델 판단이니 남겨"): on the live path (production config: originals compliance, the relation fact checker with JUDGE_ARM=single) a judge's verdict is applied as given. Removed: the compliance quote-in-original check and the cited-document check (an unknown document is applied and logged; rule_id = document + normalised section, for duplicate suppression only); the TEST-QUALIFIER drop when the result id is unknown (the model's say_instead stays); the rewrite of an out-of-scope product to the on-air one; the fact checker's no-evidence-id drop (from_relation), the unknown-evidence and approved-claims drops (D-338) and the D-346 log-only number checks (hard_validate, verify branch); the D-117 per-subject ordering drop; the merge protection of a fact note's re-show (D-088 in facts.apply_fact_check) and the rule that a line never corrects a note it re-showed. The only skip is a verdict that cannot be applied: a product id not in the show (logged), and ids the model was never given (context group, point, cue ids, a switch target, correction ids, note and alert handles), logged. Kept as the model's own verdicts: is_quoted, is_negated, the v5 stance REPORTS_OR_ASKS, relation uncertain. Kept as scheduling or display: dedupe of the same rule from one merged claim (D-088/D-118), the repeat qualifier dedupe (D-108), a stale verdict on a line said before a switch or undo (segment generation), a fix from a line older than the note's latest showing (D-364, a handle from an earlier showing), the user's switch rule (next product only, not a quote). The compliance alert now carries the model's citation and quote; the operator card shows them as "AI citation" and "AI summary". Not on the live path and unchanged (off arms): FACT_GUARDS=on post_validate, the hard_validate guards branch, the legacy rules path (validate_compliance), the verifier and vote arms. Tests: tests/test_d374.py; D-338, D-346, D-358, relation, merge and concurrency tests updated to the new behaviour.

D-375 (user, demo only): the DAON demo show (a session whose releases are the demo's own, data/demo_release/show.json) gets the demo feed again: chatter and bursts (D-278 had turned them off for every release show; other release shows still have none). A new burst B6_sample_questions in data/demo/comment_script.json posts 13 viewer questions, 2.5 s apart, through the normal comment pipeline: three common questions asked several ways (the cream's price, sensitive skin, ampoule before or after the cream), two singles the product info answers (under makeup, fragrance) and one it does not (shipping to Brunei, for the operator). The Demo Console's "Send sample questions" button fires it. The comments pipeline (triage, grouping, composer, posting) is unchanged. Tests: tests/test_d375.py (with the mock's keyword triage only the price group forms; the live triage groups by meaning), screens.test.tsx.

D-376: codex review of D-373/D-374. (1, P1) A fact note keeps its latest showing: a contradiction from an older line that arrives after a later line re-showed the note does not move the note back to the older line (facts.apply_fact_check `order`, the line's position in the show). It is ordering, not a drop: the note stays shown, and the D-364 rule (a fix older than the latest showing never closes it) holds again. (2, P2) A note with no evidence passage is keyed by the host's words, so two evidence-less notes of one field stay apart. (3, P2) A tick for the next product of the line's segment goes to that product's segment opened after the line, else pre_covered; only the product that had just left the air uses the segment right before the line's (never an older one). (4, P2) The host's fact note labels an evidence-less note of a field other than price, set price or promo as "AI fact check" with no promo condition (it was always "active promotion"). Not changed: TEST-QUALIFIER takes the recorded wording by qualified_result_id (an id mapping). Tests: two D-376 tests in tests/test_d374.py, one in tests/test_d372.py, host.test.tsx.

D-377: codex review of D-376 (P2). A prompter tick for a product other than the line's goes to that product's latest segment when it closed within the dual scope (SWITCH_DUAL_SCOPE_SEC) before the line, whatever the run-sheet order: cream -> ampoule -> cream by the operator, then the ampoule's price said right a few seconds later ticks the ampoule segment that just left (D-376 sent it to pre_covered because the ampoule is also the next product). Otherwise, a product to come: its segment opened after the line, else pre_covered; never an older segment. Tests: test_d377 in tests/test_d372.py; the D-376 test now runs on a realistic timeline (segments 30 s apart).

D-378 (user): the comments session builds its own Firestore storage for comment data, so the D-354 FirestoreStore no longer mirrors or reads back the collections only the comments pipeline writes: comments, analyses (triage), groups (question groups), answers and messages (posted messages), nor the comment agents' call rows in agent_calls (comment_triage, comment_triage_batch, answer_composer, draft_verifier, file_tools). They stay in memory only, as before D-354; the comments pipeline is unchanged. Live data still goes to Firestore: the session, segments, transcripts, alerts, events, summary and our judges' agent calls. No comment-specific Firestore code existed beyond the generic mirror; the D-354/D-361 store tests that used the comments collection as a sample now use transcripts. Tests: test_d378 in tests/test_d354.py.

D-379 (user, follow-up of D-378): the events the comments pipeline emits are not mirrored to Firestore or read back either, since they carry comment data: comment.created, comment.analyzed, comment.hidden, comment.unhidden, group.updated, hostqueue.updated (the host's question slots), message.pending, message.published, message.updated, message.cancelled and notice.updated (the pinned notice). They stay in memory and on the SSE stream. After a read-back the event seq continues from the highest stored seq + 1; the comment events are gaps. Known limit: an SSE client that saw a comment event numbered above the highest stored seq, then reconnects to a new instance, resumes after that number and misses the new instance's first events up to it. Not filtered: the session document (it holds host_slots and the pinned notice). Test: test_d379 in tests/test_d354.py.

D-380 (user, follow-up of D-379): (1) the Firestore session document no longer holds comment data: host_slots and pinned_notice are dropped from what is mirrored; they stay in memory. (2) The session document carries an event seq high-water mark (`_event_seq_hw`, the highest seq emitted, comment events included), raised on every event and coalesced with the session write in the queue. After a restart the bus starts from max(high-water mark, highest stored event) + 1 (FirestoreStore.seq_floor), so a client that saw a comment event never misses the new instance's events (fixes the D-379 known limit). Tests: test_d379 (next seq follows the last comment event) and test_d380 in tests/test_d354.py.

D-381: codex review of D-377..D-380. (1, P1) The seq high-water mark is read from the session document after its JSON fallback is decoded, so a session stored as one JSON field keeps it. (2, P2) A segment that ended before the line's segment was reopened by an undo did not just leave the air (the undone one did): cream -> ampoule -> cream -> ampoule 1 s apart, the last switch undone, then the ampoule's price said right goes to pre_covered, not to the first ampoule segment (Segment.reopened_at, set by the undo); the D-376 test is back on 1 s gaps. (3, P2) The comment agents' calls also travel as agent.call events (StoreAudit); those events are not mirrored either. (4, P2) The high-water mark is a reserved ceiling (seq + 1000) written once per 1000 events, not on every event; a new process continues after it (a gap of up to 1000 is fine). Tests: test_d381 in tests/test_d354.py, the D-376 test in tests/test_d372.py; the replay and D-361 read-back tests now expect the seq to continue past the ceiling.

D-382: codex review of D-381 (P2). A segment keeps every time an undo reopened it (Segment.reopen_times, replacing D-381's single reopened_at), and a tick is judged on the latest reopen at or before the line: a second switch and undo after the line was said (before its verdict lands) no longer turns the stale check off, so the first, stale ampoule segment is not ticked. Test: test_d382 in tests/test_d372.py (fails on D-381).

D-383 (user; 00010 show: the host said the wrinkle alert's say_instead, "helps relieve the feeling of dryness", and the judge kept the alert as "an approved compliant claim"): compliance prompt v5. Job 1 is one rule for the model, as the user asked ("just the LLM: if the host corrected it, mark it"): for each ACTIVE_ALERTS entry write {handle, fixed_by_this_line}; true if this line, in context, corrects or takes back that alert's claim, in any way (saying the suggested say_instead counts), otherwise false. The long fix and not-fix lists and the TEST-QUALIFIER detail in Job 1 are removed; Example F is one short fix (a claim taken back and replaced by the alert's say_instead). Handles stay (they only wire the answer to the alert); ACTIVE_ALERTS already carries each alert's say_instead. Job 2 is unchanged. Test: tests/test_d383.py (the judge's input carries the say_instead and the v5 rule; the model's fixed/not-fixed verdict is applied); the model's own behaviour needs a live check.
