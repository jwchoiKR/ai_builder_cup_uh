# LIVE / Studio

**A real-time compliance and fact co-pilot for live-commerce hosts, on Google Cloud.**

AI Builder Cup 2026 · Track: Retail & Commerce

While the host talks on air, it flags claims that the uploaded regulations prohibit and product facts said wrong, shows a line to say instead, and clears the warning when the host corrects it in their own words. It also keeps the prompter, the product order and viewer questions in step. The host never has to touch the screen. An operator can watch the same show from a control room, but a solo host can run without one.

## Evidence at a glance

Measured on a sealed set of 6 products the app had never seen (set 7, 10/8), host lines spoken by a TTS voice through the real Chirp 3 speech-to-text path:

| | First run (fresh set) | Second run (same set, after one change) | Pass line |
|---|---|---|---|
| Detection of prohibited claims and wrong facts | 94.0% (126 of 134) | **95.5%** (128 of 134) | ≥ 95% |
| False alerts on safe lines | 2.4% (3 of 127) | **1.6%** (2 of 127) | < 1% (not met) |
| Wrong strongest alerts | 0 | **0** | 0 |
| Alert latency p95, end of sentence to host screen | | **4.2 s** | ≤ 5 s |

- The second run added one change chosen from the first run (a line that expects an answer is judged together with the next line). The set was no longer unseen, so the fresh-set number is 94.0%.
- **Not yet measured:** the 10/9 simplification described below. The next sealed set will be run on it. Details and conditions are in [Evaluation](#evaluation).

## What happens on air

| The host says | The host screen shows |
|---|---|
| "Use it every night and your wrinkles will disappear overnight." | Red **Regulation** box: the claim, the clause of the regulation PDF it breaks, and a compliant line built only from the product's approved claims. It clears when the host corrects it, in any words. |
| "The live price is S$32 today." (the product sheet says S$36) | Orange **Product info** box: "Cream: The live price is S$36.00". It clears when the host says the right value. |
| "9 out of 10 users felt softer skin." (said without its source) | Orange box: the host's own sentence with the tester named in the product's test record. |
| "Now let me show you the toner." | The prompter moves to the next product in the run sheet at once. The operator can undo it. |
| A prompter point, said in any words | The point is ticked on the prompter. |

## How it works

```
viewer comments ─▶ comment path (triage, answer from the product record, or send to a person)

host mic ─▶ Chirp 3 streaming STT (phrase hints from the product brief)
              │ each final line, judged in parallel by three Gemini 3.5 Flash-Lite calls
              ├─▶ Compliance judge: the regulation PDFs, as original files in the prompt
              ├─▶ Fact checker:     exactly what the host prompter shows
              └─▶ Context judge:    product switch, prompter ticks, which viewer question was answered
                        │
                        ▼
              code: maps the model's handles to alert ids, merges a sentence that STT split in two,
                    runs timers, draws the host, operator, viewer and summary screens
```

- **The models judge meaning; code does not.** Whether a line breaks a regulation, whether a value is wrong, whether a later line corrected an alert, whether two alerts are the same claim and whether the host is moving on are model verdicts. On 10/9 we removed the code that used to drop, rewrite or downgrade verdicts.
- **One violation, one alert.** Each alert has a handle (A1, F1 ...). For every new line the judges say, per handle, whether this line corrected it.
- **Colour comes from the source:** a clause of a regulation document gives red; a check against the product's own documents (a fact, a test result without its source) gives orange. Both are the same size and stay until corrected.
- **No product-specific prompts or rules.** A product enters only through its documents: onboarding reads the uploaded PDFs with Gemini 3.8 Flash into a release, a Brief agent writes the prompter points and speech hints, and people only approve. Regulations are uploaded separately, as PDF.
- **Viewer comments** are answered from the product record when it answers them and sent to a person when it does not ([docs/comments.md](docs/comments.md)).

## Google Cloud

| Service | Use |
|---|---|
| Speech-to-Text V2, `chirp_3` (region `us`) | streaming transcription of the host, with phrase hints from the brief |
| Vertex AI Gemini 3.5 Flash-Lite (global endpoint) | the three live judges, with a fixed seed |
| Vertex AI Gemini 3.8 Flash | onboarding: reading product documents, the Brief agent |
| Cloud Run (us-central1, behind IAP) | the app: FastAPI backend, React screens, server-sent events; one instance |
| Firestore (`live-studio`) | show state (sessions, transcripts, alerts, segments, events), written behind memory and read back after a restart |
| Cloud Storage | approved releases, briefs and regulation packs (write-once) |
| Model Armor | screening viewer comments |

## Evaluation

**Method**
- Each round uses a new sealed set of 6 products with invented documents. The developer never sees it.
- GPT wrote the host lines and a first label for each; a separate Claude critic labelled the same lines blind. They agreed on 286 to 288 of 288 lines. Every later label change is logged with its reason.
- Host lines are spoken by a Windows TTS voice and go through the real Chirp 3 path into the app, so speech-to-text errors count.
- Pass lines hold for every product, not on average: detection ≥ 95%, false alerts < 1%, no wrong strongest alert, alert p95 ≤ 5 s.

**Set 7 in detail** (10/8, one voice)
- Scored lines: 261 of 288 (134 with a violation, 127 safe). Left out: 18 lines where two hosts speak over each other, 4 contrived stress lines, 5 lines outside the product's own regulation pack.
- Critic rulings made after the run: 2 corrections credited, 3 extra alerts not penalised. Without them the second run is 94.8% detection, 1.6% false alerts and 1 wrong strongest alert; the first run is 93.3% and 2.4%.
- Per product (second run): detection 82.6% to 100%, false alerts 0% to 4.8%. The per-product pass lines are met by 3 of 6 products for detection and 4 of 6 for false alerts.
- The 2 false alerts in the second run are both STT writing "four" as "for" next to a number.
- "Wrong strongest alert" was measured when the model still graded severity. Since 10/9 every regulation citation is red, so this line will be re-measured.

**Earlier sealed sets** (detection on unseen products): 84% (set 3, typed text, 10/5) → 91.0% (set 4, typed text) → 89.6-90.3% (set 6, first round through TTS and STT) → 94.0% (set 7, first run).

**Code rules against model judges** (set 5, same STT lines, diagnostic because the set had been seen): code gates on top of the model gave 19.4% false alerts and 5 wrong strongest alerts; model verdicts alone gave 0.9-1.9% false alerts and 1 wrong strongest alert. This is why code no longer judges meaning.

## Known limits

- False alerts are above the 1% line, and three products miss the detection line.
- Tested with TTS voices, not yet with a real human host.
- One Cloud Run instance. Show state survives a restart through Firestore; comment state is kept in memory during a show.
- No per-show cost figure yet.

## Layout

| Path | What |
|---|---|
| `backend/` | Python 3.12, FastAPI. `app/agents` the judges, `app/pipelines` the live and comment paths, `app/store` memory and Firestore, `scripts/` eval tools, `tests/` pytest |
| `frontend/` | React 18 + TypeScript + Vite: host, operator, viewer, studio, setup and summary screens |
| `prompts/` | every prompt, product-neutral, with fictional examples |
| `data/` | demo releases and the regulation PDFs shipped in the image |
| `deploy/` | `cloudrun.sh`, the deployed settings |
| `docs/` | `DECISIONS.md` (every design decision, numbered), `VERIFIED.md`, `eval/`, `decks/` |

## Run locally

1. Requirements: [uv](https://docs.astral.sh/uv/), Node.js 20+, and `gcloud auth application-default login` for Vertex AI and Speech-to-Text.
2. Copy `.env.example` to `.env` and set `GCP_PROJECT`.
3. Backend: `cd backend && uv sync`
4. Frontend: `cd frontend && npm install && npm run build`
5. Start: `cd backend && uv run uvicorn app.main:create_app --factory --port 8000`, then open <http://localhost:8000/studio>. `/api/health` shows the providers, models and store.
6. Without Google Cloud: `LLM_PROVIDER=mock STT_PROVIDER=mock`.

Deploy: `bash deploy/cloudrun.sh` (Cloud Run, Firestore database, bucket, IAP).

## Tests

```sh
cd backend && uv run pytest -q     # unit, pipeline and API tests with mock providers
cd frontend && npm test            # component and store tests
cd frontend && npm run e2e         # Playwright scenes
```
