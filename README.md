# LIVE / Studio

AI co-pilot for live-commerce broadcasts: host screen, operator control room and viewer page in one web app, driven by real-time AI agents on Google Cloud.

- **Specification:** `../DEV_SPEC.md` (in the delivered pack).
- **Records:** decisions in `docs/DECISIONS.md`, platform facts checked against official docs in `docs/VERIFIED.md`.

**Status:**
- **P0 (foundations):** done.
- **P1 (comment path):** done: prefilter, triage, grouping, routing, BM25 retrieval, composer with verification, caches, auto answers, host queue, operator actions, feed engine. Comment eval results are in `docs/eval/`.

## Layout
| Path | What |
|---|---|
| `data/`, `prompts/` | Data pack and prompt drafts, copied unchanged. Product facts only come from `data/products/`. |
| `backend/` | Python 3.12, FastAPI, single process. `app/` is the service, `scripts/` the tools, `tests/` pytest. |
| `frontend/` | React + TypeScript + Vite (phase P3). |
| `docs/` | `DECISIONS.md`, `VERIFIED.md`. |

## Run locally

Requirements:
- [uv](https://docs.astral.sh/uv/)
- Google Cloud credentials for the Vertex AI provider: `gcloud auth application-default login`

1. Copy `.env.example` to `.env` and set `GCP_PROJECT`. Every key and its default is described in DEV_SPEC §5.
2. Install the backend:
   ```sh
   cd backend
   uv sync
   ```
3. Check that both Gemini models answer with structured JSON at the configured thinking levels:
   ```sh
   uv run python scripts/check_models.py           # add --levels to list accepted thinking levels
   ```
4. Start the API:
   ```sh
   uv run uvicorn app.main:create_app --factory --port 8000
   ```
   - <http://localhost:8000/api/health> shows the providers, model ids and warm-up results.
   - `POST /api/sessions` creates a session.
   - `GET /api/sessions/{id}/events` is its event stream (SSE).
5. Without Google Cloud, set `LLM_PROVIDER=mock` and `STT_PROVIDER=mock` in `.env`. Agents then answer from `backend/tests/fixtures/llm/`.

## Tests
```sh
cd backend
uv run pytest -q
```
- Tests never read `.env` and always use mock providers.
- Recorded model outputs live in `backend/tests/fixtures/llm/`. To refresh them against Vertex AI:
  ```sh
  uv run python scripts/run_eval.py comments --record   # eval cases; writes docs/eval/<date>-comments.md
  uv run python scripts/record_demo_fixtures.py         # the demo script (scene ids as scenario tags)
  ```

## Recording the demo (DEV_SPEC §13.3)
- Reset the demo before each take.
- Record S03–S08 in one continuous take so the latency chips are credible.
- Keep the operator metrics chips visible in the frame for S07.

The full recording guide comes with phase P5.
