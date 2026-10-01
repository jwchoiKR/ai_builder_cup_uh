# Verified facts (DEV_SPEC §16)

All checks done on **2026-10-01**. Evidence types:
- **[live]**: measured against GCP project `separk-cloocus`, location `global`, with Application Default Credentials.
- **[src]**: read in the installed SDK source (`google-genai` 2.26.0, `backend/.venv`).
- **[doc]**: official documentation page fetched that day.

Notes on the docs themselves:
- `cloud.google.com/...` doc URLs now redirect (301) to `docs.cloud.google.com/...`.
- Vertex AI is now called "Gemini Enterprise Agent Platform". Its docs root is <https://docs.cloud.google.com/gemini-enterprise-agent-platform/> (written `GEAP/` below).
- Vertex AI Search is now called "Agent Search". Its API is still `discoveryengine`.

| # | Item | Phase | Status |
|---|---|---|---|
| 1 | Gemini model ids | P0 | **Verified [live] [doc]** |
| 2 | Thinking level and structured output in google-genai | P0 | **Verified [live] [src] [doc]** |
| 3 | SDK timeout, retry, cancellation | P0 | **Verified [live] [src] [doc]** |
| 4 | Speech-to-Text V2 `chirp_3` | P4 | Docs verified; live checks listed in 4.9 are due in P4 |
| 5 | Vertex AI Search | P6 | Docs verified; live checks due in P6 |
| 6 | Gemini explicit context caching | (only if tested) | Docs verified |
| 7 | Cloud Run | P6 | Docs verified |
| 8 | Firestore | P6 | Docs verified |

---

## 1. Gemini model ids: `LLM_FAST_MODEL`, `LLM_QUALITY_MODEL`

**Result: both configured ids are available in `separk-cloocus` at `global`. No change to §5 defaults.**

| Key | Id | Status [doc] | Live result [live] |
|---|---|---|---|
| LLM_FAST_MODEL | `gemini-3.5-flash-lite` | GA since 2026-07-21; retirement "July 21, 2027 or later"; served at `global`, `us`, `eu`. | HTTP 200; `modelVersion: gemini-3.5-flash-lite`. |
| LLM_QUALITY_MODEL | `gemini-3.8-flash` | GA since 2026-09-02; no retirement date; served at `global`, `us`, `eu`. | HTTP 200; `modelVersion: gemini-3.8-flash`. |

- Both models have a 1,048,576-token context and up to 65,536 output tokens. [doc]
- The `global` endpoint has better availability and fewer 429s. It gives no control over where processing happens. [doc]
- Other current ids, in case a fallback is ever needed [doc]:
  - Flash: `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash` (all GA).
  - Flash-Lite: `gemini-3.1-flash-lite` (GA).
  - Not for use: `gemini-2.5-flash` and `gemini-2.5-flash-lite` retire on 2026-10-20.
- Re-check any time with `uv run python scripts/check_models.py`. The result on 2026-10-01 was PASS (see 2.4).

Sources:
- GEAP/models/gemini/3-5-flash-lite: <https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-flash-lite>
- GEAP/models/gemini/3-8-flash: <https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-flash>
- GEAP/resources/locations: <https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations>

## 2. Thinking level and structured JSON output (installed `google-genai` 2.26.0)

### 2.1 Client
- The documented constructor is `genai.Client(enterprise=True, project=..., location=...)`. `vertexai=True` is documented as a "Legacy flag for `enterprise`" [src] [doc]. **We use `enterprise=True`.** (D-007)
- The async client is `client.aio`. It is closed with `await client.aio.aclose()`. [doc]
- By default the SDK calls the `v1beta1` REST path (`.../v1beta1/projects/.../publishers/google/models/...:generateContent`). [live]

### 2.2 Thinking
- The field is `types.ThinkingConfig(thinking_level=...)`. `types.ThinkingLevel` values are `MINIMAL`, `LOW`, `MEDIUM`, `HIGH`, `THINKING_LEVEL_UNSPECIFIED`. It is a case-insensitive enum. [src]
- `thinking_budget` also exists. Gemini 3 models use `thinking_level`, and sending both fields is an error. [doc]
- Levels per model [doc], confirmed [live] with `scripts/check_models.py --levels`:

  | Model | MINIMAL | LOW | MEDIUM | HIGH | Default |
  |---|---|---|---|---|---|
  | gemini-3.5-flash-lite | ok | ok | ok | ok | MINIMAL |
  | gemini-3.8-flash | **400 INVALID_ARGUMENT** "Thinking level is unsupported: THINKING_LEVEL_MINIMAL" | ok | ok | ok | MEDIUM |

  The configured values (`MINIMAL` for fast, `MEDIUM` for quality) are valid. **Never set `LLM_QUALITY_THINKING=MINIMAL`** while the quality model is `gemini-3.8-flash`.
- Thinking tokens count toward `max_output_tokens`. [live]
  - Example: `gemini-3.8-flash` with a 64-token cap spent 59 tokens thinking and stopped with `MAX_TOKENS`.
  - So we do not set `max_output_tokens`.
- At MINIMAL and LOW, `gemini-3.5-flash-lite` reported no thought tokens. At MEDIUM it used 164 and at HIGH 193 (tiny prompt). [live]

### 2.3 Temperature
The spec (§7.1) says to set temperature 0. The docs say otherwise [doc]:
- For `gemini-3.5-flash-lite`: custom temperature/top-K/top-P "aren't supported ... that value will be ignored".
- For `gemini-3.8-flash`: temperature, top_k and top_p "are ignored by the backend".
- For Gemini 3 in general: "strongly recommended to keep the temperature parameter at its default value of 1.0 ... setting it to less than 1.0 may lead to unexpected behavior, such as looping or degraded performance."
- What happened live: sending `temperature=0` was accepted (HTTP 200).

**Decision D-008: temperature is not sent.**

### 2.4 Structured output
- The fields are `GenerateContentConfig.response_mime_type="application/json"` plus **either** `response_schema` (OpenAPI subset; also accepts a pydantic class) **or** `response_json_schema` (JSON Schema dict). [src] [doc]
- Keywords `response_json_schema` supports [doc]:
  - `$id`, `$defs`, `$ref`, `$anchor`, `type`, `format`, `title`, `description`
  - `enum` (strings and numbers), `items`, `prefixItems`, `minItems`, `maxItems`, `minimum`, `maximum`
  - `anyOf`, `oneOf` (treated as anyOf), `properties`, `additionalProperties`, `required`, `propertyOrdering`
  - Other keywords are ignored.
- A pydantic `model_json_schema()` with nested models (`$defs`/`$ref`), `Literal` enums, `X | None` (anyOf with null) and `dict[str, str | None]` worked on both models. [live]
- **`response_schema=<pydantic class>` silently returned `{}` for a `dict[str, str | None]` field. `response_json_schema` filled it correctly.** Latency was the same for both modes. [live]
  - Warm `gemini-3.5-flash-lite` at MINIMAL: 1.3–1.6 s.
  - `gemini-3.8-flash` at MEDIUM: 3.7–6.6 s (about 450-token prompt).
- `response.parsed` swallows `ValidationError` and `JSONDecodeError` and can be `None`. [src]
- **Decision D-005:** we send `response_json_schema=Model.model_json_schema()` and validate `response.text` with our pydantic model ourselves.
- REST marks `responseSchema`, `responseJsonSchema` and `responseMimeType` as deprecated in favour of `responseFormat`. SDK 2.26.0 has no `response_format` field yet, so we keep the SDK field. Re-check when the SDK is upgraded. [doc] [src]
- `check_models.py` result, 2026-10-01 [live]:
  - Both models returned schema-valid JSON with the right product id and the catalog price `S$32.00`. PASS.
  - Cold first call: 6.4 s (flash-lite) and 3.1 s (flash).
  - Warm call: 0.94 s (flash-lite, MINIMAL) and 2.3 s (flash, MEDIUM).
  - Server warm-up calls at startup: about 4.7 s each.
  - Cold calls can be much slower: one first call took 32 s. **Warm-up (§7.1) is required.**

Sources:
- GEAP/models/thinking: <https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/thinking>
- GEAP/models/guides/gemini-3-8-flash: <https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-3-8-flash>
- GEAP/models/start/get-started-with-gemini-3: <https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start/get-started-with-gemini-3>
- GEAP/models/capabilities/control-generated-output: <https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/control-generated-output>
- GEAP/reference/rest/v1/GenerationConfig: <https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/GenerationConfig>
- SDK reference: <https://googleapis.github.io/python-genai/genai.html>
- SDK source: <https://github.com/googleapis/python-genai/blob/v2.26.0/google/genai/_api_client.py> and `types.py`, `client.py`, `_transformers.py`
- PyPI (google-genai 2.26.0, uploaded 2026-09-30): <https://pypi.org/pypi/google-genai/json>

## 3. Request timeout, retries, and dangling requests

### 3.1 Timeout
- `types.HttpOptions(timeout=...)` is an integer in **milliseconds**. [src] [doc]
- It can be set per request through `GenerateContentConfig.http_options`.
- The SDK converts it to seconds for httpx and also sends an `X-Server-Timeout` header (seconds, rounded up). [src]
- When it expires, the SDK raises `httpx.ReadTimeout`, not an `APIError`. Measured at 503 ms for a 500 ms setting. [live]

### 3.2 Retry
- **Retry is off by default.** With `retry_options=None`, the SDK uses `tenacity.stop_after_attempt(1)`. [src]
- `types.HttpRetryOptions` fields and their defaults when given [src] [doc]:
  - `attempts=5` (includes the first call)
  - `initial_delay=1.0`, `max_delay=60.0`, `exp_base=2`, `jitter=1`
  - `http_status_codes`: 408, 429, 500, 502, 503, 504
- **Trap:** when enabled, the SDK also retries `httpx.TimeoutException` and `httpx.ConnectError`, whatever `http_status_codes` says. [src]
  - This would retry on timeout, which §7.1 forbids.
- **Decision D-006:** SDK retry stays off. `LLMClient` retries once on `errors.ServerError` (5xx) only, inside the same agent deadline.
- Error classes: `errors.ClientError` for 4xx, `errors.ServerError` for 5xx, both subclasses of `errors.APIError` with `.code` and `.status`. Example: unknown model gives `ClientError 404 NOT_FOUND`. [src] [live]

### 3.3 Cancellation and dangling requests
- The async client uses **aiohttp if it is importable**, else httpx. We do not install aiohttp, so it uses `AsyncHttpxClient`. [src] [live]
  - The aiohttp path also silently retries once on connection errors. [doc] [src]
  - **Keep aiohttp out of the dependencies.**
- Live test [live]:
  1. `asyncio.wait_for(client.aio.models.generate_content(...), 0.5)` on a slow request (`gemini-3.8-flash`, HIGH).
  2. It raised `TimeoutError` after 494 ms.
  3. 200 ms later, the httpx pool had **0 connections and 0 requests in flight**, and no extra asyncio tasks remained.
  4. The same client then answered the next call normally (843 ms).
- **Conclusion:** cancelling the coroutine closes the HTTP request; nothing dangles.

### 3.4 `X-Server-Timeout` causes early 504s (found in P2, 2026-10-01) [live]
- **What happened:** with `HttpOptions.timeout=2500`, the SDK sends `X-Server-Timeout: 3`. Vertex then answered `504 DEADLINE_EXCEEDED` after only **1.2–1.6 s**, on 3 of 9 judge calls in a probe and 2 of 39 in the first utterance eval.
- **Same calls without the header:** 9/9 succeeded in 1.2–1.7 s.
- **Later run:** the 39-case utterance eval had 0 timeouts.
- **Decision D-047:** we do not set `HttpOptions.timeout`. The agent deadline is enforced only by `asyncio.wait_for`, whose cancellation closes the request (3.3).
- **504 handling:** a 504 `DEADLINE_EXCEEDED` is treated as a timeout and never retried (D-044).

## 4. Speech-to-Text V2, model `chirp_3` (for P4)

Pages, all fetched 2026-10-01:
- [C3] <https://docs.cloud.google.com/speech-to-text/v2/docs/chirp_3-model> (page updated 2026-09-30)
- [LANG] <https://docs.cloud.google.com/speech-to-text/docs/speech-to-text-supported-languages>
- [Q] <https://docs.cloud.google.com/speech-to-text/docs/quotas>
- [VAD] <https://docs.cloud.google.com/speech-to-text/docs/voice-activity-events>
- [RPC] <https://docs.cloud.google.com/speech-to-text/docs/reference/rpc/google.cloud.speech.v2>
- [PY] <https://docs.cloud.google.com/python/docs/reference/speech/latest/>
- [RN] <https://docs.cloud.google.com/speech-to-text/docs/release-notes>

### 4.1 Streaming
`StreamingRecognize` is supported for chirp_3. [C3]
- Utterance-level timestamps exist only in streaming.
- Diarization and word-level timestamps exist only in Recognize/BatchRecognize.

### 4.2 Locations
- GA regions are `us` and `eu` (multi-regions) [C3] [LANG].
- Preview regions since 2025-11-13: asia-south1, europe-west2, europe-west3, northamerica-northeast1 [RN].
- `asia-southeast1` and `global` are not listed for chirp_3.
- **`STT_LOCATION=us` is correct.**
- Endpoint: `ClientOptions(api_endpoint="us-speech.googleapis.com")`.
- Recognizer: `projects/{project}/locations/us/recognizers/_`. [C3] [RPC]

### 4.3 Languages
- `en-US` is GA.
- **`en-SG` is not supported by chirp_3**; it is listed only for `telephony`/`telephony_short`. [LANG]
- **Keep `STT_LANGUAGE=en-US`**, as §5 says.
- `language_codes=["auto"]` exists but is not needed.

### 4.4 Features [C3]
- **Automatic punctuation:** GA (`RecognitionFeatures.enable_automatic_punctuation`).
- **Word time offsets:** **not supported** for chirp_3. Do not rely on `enable_word_time_offsets`.
- **Result timing:** `StreamingRecognitionResult.result_end_offset` exists [RPC]. Use it for `speech_end_at` (§10.2) and verify it live.
- **Voice activity events:** `enable_voice_activity_events=True` appears in the chirp_3 streaming sample.
- **Voice activity timeout:** `voice_activity_timeout` must be between 500 ms and 60 s, and it closes the stream [VAD]. Not needed.
- **Interim results:** `streaming_features.interim_results` exists [RPC]. The chirp_3 sample sets it to False, and no page states chirp_3 support. **Must test live.**
- **Endpointing (relevant to the ≤5 s budget):** `streaming_features.endpointing_sensitivity` has STANDARD (default), SHORT ("faster response ... reasonable sentence-level accuracy") and SUPERSHORT (single words). It needs `google-cloud-speech>=2.37`. **Try SHORT in P4.**

### 4.5 Adaptation / phrase hints
- Supported (GA) through inline `SpeechAdaptation(phrase_sets=[AdaptationPhraseSet(inline_phrase_set=PhraseSet(phrases=[{"value": ...}]))])`. [C3]
- chirp_3 limit: "up to 1,000 phrases ... use as few entries as possible". [C3]
- General limits [Q]:
  - boost 0–20
  - 1,200 phrases per PhraseSet, 5,000 per request
  - 100 characters per phrase
- Whether chirp_3 honours `boost` is **not stated**; test live.

### 4.6 Limits
- A stream lasts at most **5 minutes**, and audio must be sent at roughly real time. [Q]
- The pages disagree on max audio per request: 25 KB [Q], 15,360 bytes [VAD], 15 KB [RPC].
- Our 100 ms frame of 16 kHz mono LINEAR16 is 3,200 bytes, which is safe under all of them. 100 ms is also Google's recommended frame size.
- The first request carries only `recognizer` and `streaming_config`; later requests carry only `audio`. [RPC]
- Quota: 3,000 requests per minute per project and 300 concurrent sessions [Q]. One 100 ms stream sends 600 requests per minute, which is fine for one host.

### 4.7 Restart method
- The official V2 infinite-streaming sample: <https://github.com/GoogleCloudPlatform/python-docs-samples/blob/main/speech/microphone/transcribe_streaming_infinite_v2.py>.
- How it works:
  1. It ends each stream proactively at 240 s.
  2. It keeps the audio sent since the last final result (tracked with `result_end_offset`).
  3. It re-sends that tail at the start of the next stream ("bridging").
  4. It corrects timestamps as `result_end + limit × restarts − bridging offset`.
- Use the same method in P4.

### 4.8 Python names
- **Confirmed:**
  - `StreamingRecognizeRequest(recognizer, streaming_config)`
  - `StreamingRecognitionConfig(config, streaming_features)`
  - `RecognitionConfig(explicit_decoding_config, language_codes, model, features, adaptation)`
  - `ExplicitDecodingConfig(encoding=ExplicitDecodingConfig.AudioEncoding.LINEAR16, sample_rate_hertz=16000, audio_channel_count=1)`
  - `StreamingRecognitionFeatures(interim_results, enable_voice_activity_events, voice_activity_timeout, endpointing_sensitivity)`
- **Async client:** `SpeechAsyncClient.streaming_recognize(requests=AsyncIterator[...])`. [C3] [PY]
- **Version:** latest `google-cloud-speech` is 2.40.0 (2026-06-03). Pin `>=2.37`.

### 4.9 Live checks due in P4
- interim results with chirp_3
- `result_end_offset` values
- SHORT endpointing latency
- phrase hints effect and boost
- 4-minute restart without lost audio

### 4.10 Live results (P4, 2026-10-01) [live]
**Setup:** synthesized en-US speech (Windows SAPI, 16 kHz mono LINEAR16) streamed at real-time pace to `us-speech.googleapis.com`, recognizer `projects/separk-cloocus/locations/us/recognizers/_`, `chirp_3`, `en-US`, automatic punctuation.

- **Interim results:** with `interim_results=True`, chirp_3 returned **no interim results**, only finals. The operator's interim transcript line therefore stays empty with chirp_3.
- **`result_end_offset`:** filled on every final. `providers/stt.py` maps it to the arrival time of the audio at that offset to get `speech_end_at`.
- **Endpointing:**

  | Setting | Final after the sentence | End offset |
  |---|---|---|
  | `ENDPOINTING_SENSITIVITY_STANDARD` | 6.2 s | 5.08 s |
  | `ENDPOINTING_SENSITIVITY_SHORT` | 5.7 s | 4.64 s |

  Both on the same 10 s clip. **SHORT is used.** Side effect: longer sentences arrive as two or three finals.
- **Speech end → final:** 0.78–1.40 s (10 sentences); p50 0.88 s, p95 1.04–1.69 s in two full-script runs.
- **Adaptation:** inline phrase sets are accepted together with chirp_3, with no error.
  - "DAON LAB" was recognised as "DAON web" once without hints (STANDARD), and correctly with hints.
  - `boost` was not tested and is not sent.
- **Restart, tested live with the limits scaled down** (hard 20 s, soft 12 s; three sentences over about 45 s; 2 restarts):
  - **First version:** restarted at the hard limit only and re-sent all audio since the last final. Every sentence was recognised once, but finals right after a restart came 3.7–4.2 s after speech end, against 1.0 s before.
  - **Current version (D-071):** restarts at the first final after the soft limit, and re-sends at most the last 5 s of unfinalized audio. Finals after a restart now come 0.9–1.9 s after speech end.
  - **Speech end accuracy:** `speech_end_at` is within 0.1–0.4 s of the real end of the audio.
  - **Remaining risk:** a restart at the hard limit can split a sentence ("This one has" / "10% niacinamide"). With the real limits (soft 180 s, hard 240 s) the soft restart has a 60 s window to find a pause.

## 5. Vertex AI Search (Agent Search) (for P6)

### 5.1 Data store and metadata
- PDF is supported: up to 200 MB per file and 100,000 files per import. [doc]
- To attach metadata, import a JSONL/NDJSON metadata file with `GcsSource(input_uris=[...], data_schema="document")`. Each line looks like:

  ```json
  {"id":"<id>","structData":{"product_id":"...","doc":"..."},"content":{"mimeType":"application/pdf","uri":"gs://<bucket>/products/<file>.pdf"}}
  ```

  Use `reconciliation_mode=INCREMENTAL`. [doc]
- With auto-detected schemas, new fields become indexable automatically. The filter page still tells you to mark the field Indexable (Data > Schema). **Check it in the console.** [doc]

### 5.2 Filtering
- Syntax: `product_id: ANY("cream_hydra_barrier")`, combined with AND/OR/NOT. [doc]
- The page is inconsistent about whether to write `structData.product_id` or `product_id`. **Test both forms.**
- `SearchRequest` fields: `serving_config`, `query`, `page_size`, `filter`, `content_search_spec`, among others.
- Serving config path: `projects/{p}/locations/{loc}/collections/default_collection/engines/{engine}/servingConfigs/default_config`.

### 5.3 Chunk results
- Chunking is enabled at data-store creation only, with `documentProcessingConfig.chunkingConfig.layoutBasedChunkingConfig{chunkSize: 100-500 (default 500), includeAncestorHeadings}` and `layoutParsingConfig`.
- `ContentSearchSpec.search_result_mode=CHUNKS` returns `SearchResult.chunk` with these fields:
  - `name` (`.../documents/{document_id}/chunks/{chunk_id}`)
  - `id`, `content`
  - `relevance_score`
  - `document_metadata` (`uri`, `title`, `struct_data`)
  - `page_span`
  - `chunk_metadata`
- Adjacent chunks: the pages give the maximum as 3 or 5; use ≤3.
- Whether `struct_data` is filled in chunk results is **not confirmed**. Verify live.
- Our passage id will be `f"{code}#vs#{chunk.id}"` (§9.3).

### 5.4 Latency
No numeric latency is documented. Measure in P6.

### 5.5 Version
`google-cloud-discoveryengine` 0.20.4 (PyPI, 2026-09-17).

### 5.6 Sources
- <https://docs.cloud.google.com/generative-ai-app-builder/docs/prepare-data>
- <https://docs.cloud.google.com/generative-ai-app-builder/docs/create-data-store-es>
- <https://docs.cloud.google.com/generative-ai-app-builder/docs/provide-schema>
- <https://docs.cloud.google.com/generative-ai-app-builder/docs/filter-search-metadata>
- <https://docs.cloud.google.com/generative-ai-app-builder/docs/parse-chunk-documents>
- <https://docs.cloud.google.com/generative-ai-app-builder/docs/preview-search-results>
- <https://docs.cloud.google.com/python/docs/reference/discoveryengine/latest/google.cloud.discoveryengine_v1.types.SearchRequest>
- <https://docs.cloud.google.com/python/docs/reference/discoveryengine/latest/google.cloud.discoveryengine_v1.types.Chunk>

## 6. Gemini explicit context caching (§8.12.4; `LLM_CONTEXT_CACHE=false` by default)

Source: GEAP/models/context-cache/context-cache-overview, <https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/context-cache/context-cache-overview>. [doc]

- Both configured models support **implicit** caching, which is **on by default**: cached input tokens get a 90% discount, and nothing is needed in code. Both also support explicit caching.
- Minimum tokens for a cache, verbatim: "Gemini 3 family models: 4,096 tokens; Gemini 3.0 Flash Preview, 3.1 Pro Preview, 3.7 Flash, and 3.8 Flash (implicit caching only): 6,144 tokens".
- Explicit cache TTL: default 60 min, minimum 1 min, no maximum. Maximum size is 10 MB. Use it with the SDK field `GenerateContentConfig.cached_content`.
- **Effect on our prompts:**
  - Implicit caching matches on prompt prefixes. Our static system instruction comes first, and each user message starts with static catalog/rules blocks.
  - The utterance judge's static prefix is about 8.2 k characters plus the rules JSON. That may or may not reach the 4,096-token minimum; measure `cached_content_token_count` in P2.
  - `LLMClient` logs `usage.cached` for this.

## 7. Cloud Run (for P6)

| Topic | Fact | Source |
|---|---|---|
| WebSockets | Supported with no extra configuration. Treated as long-running requests and **subject to the request timeout**. Clients must reconnect. Do not enable end-to-end HTTP/2. An open WebSocket keeps CPU allocated. Up to 1,000 concurrent connections per container. | <https://docs.cloud.google.com/run/docs/triggering/websockets> |
| SSE / streaming | Supported with no configuration; the response must be `Transfer-Encoding: chunked` (ours is, see 2.4 live run). HTTP/2 requests are downgraded to HTTP/1 by default, so end-to-end HTTP/2 is not needed. Nothing is documented about proxy buffering. | <https://docs.cloud.google.com/run/docs/triggering/https-request>, <https://cloud.google.com/blog/products/serverless/cloud-run-now-supports-http-grpc-server-streaming> |
| Request timeout | Default 300 s, maximum 3,600 s (`--timeout`). On timeout the client gets a 504; the instance keeps running. SSE and the audio WebSocket must reconnect before or at the limit. | <https://docs.cloud.google.com/run/docs/configuring/request-timeout> |
| Session affinity | `--session-affinity`; cookie with a 30-day TTL; **best effort**, broken if the instance ends or is saturated. | <https://docs.cloud.google.com/run/docs/configuring/session-affinity> |
| Background work | Our asyncio timers and feed need **instance-based billing** (`--no-cpu-throttling`). With request-based billing, CPU is throttled outside requests. Also set `--min-instances 1`. Idle instances can still be shut down (10 s SIGTERM grace). | <https://docs.cloud.google.com/run/docs/configuring/billing-settings>, <https://docs.cloud.google.com/run/docs/tips/general>, <https://docs.cloud.google.com/run/docs/configuring/min-instances> |

## 8. Firestore, Native mode (for P6)

| Topic | Fact | Source |
|---|---|---|
| Transactions | 270 s time limit, 60 s idle expiration, 20 s lock deadline, 10 MiB request size, 500 field transforms per document per commit. The old "500 writes per transaction" limit is no longer listed. Python `AsyncTransaction(max_attempts=5)` and the `async_transactional` decorator. Standard edition uses pessimistic locking by default, Enterprise optimistic. Under contention the client retries, then fails with `ABORTED`. | <https://docs.cloud.google.com/firestore/quotas>, <https://docs.cloud.google.com/firestore/native/docs/manage-data/transactions>, <https://docs.cloud.google.com/firestore/native/docs/transaction-data-contention>, <https://docs.cloud.google.com/python/docs/reference/firestore/latest/google.cloud.firestore_v1.async_transaction> |
| Single-document write rate | No fixed number. Sustained high write rates to one document cause contention and hotspots; the counters sample assumes about 1 increment per second per shard. | <https://docs.cloud.google.com/firestore/native/docs/best-practices>, <https://docs.cloud.google.com/firestore/native/docs/solutions/counters>, <https://docs.cloud.google.com/firestore/native/docs/understand-reads-writes-scale> |
| Sequential ids and fields | "Do not use monotonically increasing document IDs." An indexed, sequentially increasing field limits the collection to about 500 writes per second unless it is exempted from indexing. | <https://docs.cloud.google.com/firestore/native/docs/best-practices> |
| Version | `google-cloud-firestore` 2.33.0 (PyPI, 2026-09-29). | PyPI |

**What this means for the event sequence numbers (§3.6):**
- A per-session counter document incremented in a transaction per event would contend during comment bursts (several events per second).
- The bus assigns `seq` in-process instead: one process per session, as §4.1 and Cloud Run session affinity provide (D-018).
- For the Firestore store in P6, write events with automatic document ids and a `seq` field, or keep zero-padded ids at our low rate. Decide in P6 with a load test.
