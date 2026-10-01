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
