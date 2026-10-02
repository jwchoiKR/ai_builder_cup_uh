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

