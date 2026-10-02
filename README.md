# LIVE / Studio

AI co-pilot for live-commerce broadcasts: host screen, operator control room and viewer page in one web app, driven by real-time AI agents on Google Cloud.

- **Specification:** `../DEV_SPEC.md` (in the delivered pack).
- **Records:** decisions in `docs/DECISIONS.md`, platform facts checked against official docs in `docs/VERIFIED.md`.

**Status:**
- **P0 (foundations):** done.
- **P1 (comment path):** done: prefilter, triage, grouping, routing, BM25 retrieval, composer with verification, caches, auto answers, host queue, operator actions, feed engine.
- **P2 (utterance path):** done: transcript injection, reflex, utterance judges (split3: compliance and context judges in parallel, D-099; split and single kept), fact checker, compliance and fact alerts with escalation, host-answer publishing, prompter coverage, product switch with undo, cues, metrics.
- **P3 (screens):** done: design tokens and themes, Host, Operator, Viewer, Studio with Demo Console, Hub. Scene screenshots are in `docs/screens/`.
- **P4 (audio, setup, summary):** done: microphone capture, audio WebSocket, Speech-to-Text V2 `chirp_3` streaming with restarts and phrase hints, `/setup` with the Brief Agent and glossary confirmation, summary statistics and AI recap on `/summary`.
- **P5 (hardening):** done: Playwright end-to-end test, split vs single report, latency report, rehearsal report (`docs/eval/`, `docs/rehearsal.md`).
- **P6 (Cloud Run, Firestore, Vertex AI Search):** not started.

## Layout
| Path | What |
|---|---|
| `data/`, `prompts/` | Data pack and prompt drafts, copied unchanged except the set's `short_name` in `products.json` (D-085). Product facts only come from `data/products/`. |
| `backend/` | Python 3.12, FastAPI, single process. `app/` is the service, `scripts/` the tools, `tests/` pytest. |
| `frontend/` | React 18 + TypeScript + Vite. `src/app` store, API, SSE and mic; `src/screens` all screens; `e2e/` Playwright test, scene capture, voice rehearsal. |
| `docs/` | `DECISIONS.md`, `VERIFIED.md`, `eval/`, `rehearsal.md`, `screens/`. |

## Run locally

Requirements:
- [uv](https://docs.astral.sh/uv/) and Node.js 20+
- Google Cloud credentials for Vertex AI and Speech-to-Text: `gcloud auth application-default login`
- Microsoft Edge or Chrome for the browser tests

1. Copy `.env.example` to `.env` and set `GCP_PROJECT`. Every key is described in DEV_SPEC §5, plus `COMPOSER_THINKING` (D-067) and `UTTERANCE_MERGE_WINDOW_MS` (D-088).
2. Install the backend:
   ```sh
   cd backend
   uv sync
   ```
3. Check that the Gemini models answer with structured JSON at the configured thinking levels:
   ```sh
   uv run python scripts/check_models.py           # add --levels to list accepted thinking levels
   ```
4. Build the frontend:
   ```sh
   cd frontend
   npm install
   npm run build
   ```
5. Start the app:
   ```sh
   cd backend
   uv run uvicorn app.main:create_app --factory --port 8000
   ```
   - It serves `frontend/dist` and the API.
   - <http://localhost:8000/api/health> shows the providers, model ids and warm-up results.
6. Without Google Cloud, set `LLM_PROVIDER=mock` and `STT_PROVIDER=mock`. Agents then answer from the recorded outputs in `backend/tests/fixtures/llm/`, and the microphone is off (host lines are injected).

## Screens
**Pages:**
- `/` Hub: links, new demo session, reset.
- `/studio`: Host, Operator and Viewer side by side.
  - Layout: `?layout=all|host_operator|host_viewer`.
  - **D**: Demo Console. **R**: recording mode (hides labels and console).
- `/host`: keys **Esc** (cancel switch), **M** (microphone), **T** (theme).
- `/operator`, `/viewer`.
- `/setup`: documents (an upload shows each processing stage, D-093), Brief Agent, glossary (terms can be edited or added before confirming, D-094).
- `/summary`: post-broadcast summary, AI recap first; **Export PDF** saves it as a report through the print dialog (D-097).

**Session selection:** add `?session=<id>` to any page. The default is the latest demo session.

**Frontend development:** `npm run dev` serves on <http://localhost:5173> and proxies `/api` to :8000. Set `API_TARGET` to proxy elsewhere.

## Tests
```sh
cd backend && uv run pytest -q          # unit, pipeline and API tests (mock providers, never reads .env)
cd frontend && npm test                 # component and store tests (vitest)
cd frontend && npm run e2e              # Playwright, all scenes S01-S14 (backend with mock providers on E2E_BASE, default :8002)
```

**End-to-end test:**
- Start the backend for it with:
  ```sh
  LLM_PROVIDER=mock STT_PROVIDER=mock uv run uvicorn app.main:create_app --factory --port 8002
  ```
  Or set `E2E_START=1` and the test starts it.
- The tests use the installed Edge (`channel: "msedge"`).

**Recorded model outputs** live in `backend/tests/fixtures/llm/`. To refresh them or the reports against Vertex AI:
```sh
uv run python scripts/run_eval.py comments --record          # docs/eval/<date>-comments.md (--runs 5 for min/mean)
uv run python scripts/run_eval.py utterances --mode split --runs 30
uv run python scripts/eval_composer.py                       # docs/eval/composer-thinking.md
uv run python scripts/record_demo_fixtures.py                # the demo script (scene ids as scenario tags)
```

**Voice rehearsal** (real STT and models, synthetic Windows SAPI voice; results in `docs/rehearsal.md`):
```sh
cd frontend
node e2e/rehearsal-voice.mjs alerts       # 10 HIGH-risk sentences, alert latency
node e2e/rehearsal-voice.mjs script 2     # the full host script twice
```

## Recording the demo (DEV_SPEC §13, §14.5)
**Before recording:**
1. **Real models:** `LLM_PROVIDER=vertex`, `STT_PROVIDER=google_v2`, `GCP_PROJECT` set. Run `check_models.py`, then start the app and wait until `/api/health` shows `warmup: ok` for both models.
2. **S01:** open `/setup`, run the Brief Agent for both products and press **Confirm glossary**. The confirmed terms become speech hints for the next microphone stream.

**Setting up the take:**
1. Open `/studio?layout=all` at 1920×1080 (or `host_operator` for a two-pane video). Press **R** for recording mode.
2. Keep a second window with the Demo Console open: `/studio`, then **D**. It fires bursts, starts the time sale and injects lines if needed.
3. **Reset the demo before each take** (Demo Console → Reset demo, or Hub → Reset demo).
4. Start the microphone: Demo Console → Mic **Start**, or **M** on `/host`. The host mic dot turns green and shows the input level. Allow the browser's microphone prompt the first time.

**During the take:**
- Follow `data/demo/host_script.md` scene by scene.
- Press **Start broadcast** in the operator pane (S02).
- Speak the host lines.
- Fire bursts B1–B4 at their scenes, and press **Arm B5 Switch boundary** before the ampoule introduction in S12.
- **Record S03–S08 in one continuous take**, so the latency chips are credible.
- **Keep the operator metrics chips visible for S07** ("Alert in X.Xs" measures speech end → host render).
- Pause briefly after each sentence. The speech recogniser finalises at pauses. A sentence split into two finals is judged as one (D-088), as long as the second part follows within 3.5 s.
- **Correcting a red alert:** say the approved wording shown under "Say this instead", or take the claim back explicitly ("your wrinkles won't disappear overnight"). "I'm sorry" alone does not clear it (D-089).
- **Moving to the next product:** first a transition that names it ("Now let me show you our Deep Hydration Ampoule"), then, in a later sentence, one of its facts ("It has four percent niacinamide"). Then a 5 s countdown runs, which Esc cancels (D-090).

**Ending:** press **End broadcast** (S14). Then open the summary from the operator header or the Demo Console (Open summary). The AI recap appears when the summary agent finishes.

**If something goes wrong:**
- A wrong alert can be dismissed by the operator ("Dismiss false alert").
- A wrong switch can be undone within 60 s ("Undo switch").
- Every action is logged in the event stream.

**Backup if Vertex AI or Speech-to-Text is unavailable on recording day:**
- Start the app with `LLM_PROVIDER=mock STT_PROVIDER=mock`.
- The agents then replay one complete, clean Vertex AI run of the host script (`record_demo_fixtures.py`, every agent call ok), so S02–S14 show real model outputs.
- Host lines are injected from the Demo Console instead of spoken. The latency chips then show near-zero mock latencies, so do not use this mode for the S03–S08 latency take.
- To refresh the backup, run `uv run python scripts/record_demo_fixtures.py` until it prints `RUN CLEAN`, then `uv run pytest tests/test_demo_script_api.py` and `npm run e2e`.
