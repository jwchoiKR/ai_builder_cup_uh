# LIVE / Studio

**A real-time compliance and fact co-pilot for live-commerce hosts, on Google Cloud.**

AI Builder Cup 2026 · Track: Retail & Commerce

While the host talks on air, it flags claims that the uploaded regulations prohibit and product facts said wrong, shows a line to say instead, and clears the warning when the host corrects it in their own words. It also keeps the prompter, the product order and viewer questions in step. The host never has to touch the screen. An operator can watch the same show from a control room, but a solo host can run without one.

## Evidence at a glance

Measured on a sealed set of 4 products the app had never seen (set 10, 10/14-15), 162 natural host lines in English and Korean, spoken by a TTS voice through the real Chirp 3 speech-to-text path, on the current judge setting:

| | Result | Pass line |
|---|---|---|
| Detection of prohibited claims and wrong facts | **96.3%** (52 of 54) | ≥ 95% |
| False alerts on safe lines | **0%** (0 of 108) | < 1% |
| Red (regulation) alert on a line without a regulation problem | **0** | 0 |
| Compliance judge, one call p50 / p95 | **1.4 / 2.9 s** | ≤ 5 s |
| Fact checker, one call p50 / p95 | 6.0 / 31.5 s (slow Gemini night) | ≤ 5 s (not met) |

- Three more runs on the same set with other compliance settings, on a normal Gemini day: 100% detection and 0-0.9% false alerts each.
- Per product, per line (ids and outcomes, no sealed text), alert times and the conditions: [docs/eval/sealed-set-10-results.md](docs/eval/sealed-set-10-results.md).

## What happens on air

| The host says | The host screen shows |
|---|---|
| "Use it every night and your wrinkles will disappear overnight." | Red **Regulation** box: the claim, the clause of the regulation PDF it breaks, and a compliant line built only from the product's approved claims. It clears when the host corrects it, in any words. |
| "The live price is S$32 today." (the product sheet says S$36) | Orange **Product info** box: "Cream: The live price is S$36.00". It clears when the host says the right value. |
| "Now let me show you the toner." | The prompter moves to the next product in the run sheet at once. The operator can undo it. |
| A prompter point, said in any words | The point is ticked on the prompter. |

## How it works

```
viewer comments ─▶ comment path (triage, answer from the product record, or send to a person)

host mic ─▶ Chirp 3 streaming STT (phrase hints from the product brief)
              │ each final line, judged in parallel by four Gemini calls
              ├─▶ Compliance judge: the regulation PDFs, as original files in the prompt
              ├─▶ Fact checker:     exactly what the host prompter shows
              ├─▶ Context judge:    product switch, which viewer question was answered
              └─▶ Prompter judge:   which prompter points the host has covered
                        │
                        ▼
              code: maps the model's handles to alert ids, merges a sentence that STT split in two,
                    runs timers, draws the host, operator, viewer and summary screens
```

- **The models judge meaning; code does not.** Whether a line breaks a regulation, whether a value is wrong, whether a later line corrected an alert, whether two alerts are the same claim and whether the host is moving on are model verdicts. On 10/9 we removed the code that used to drop, rewrite or downgrade verdicts.
- **One violation, one alert.** Each alert has a handle (A1, F1 ...). For every new line the judges say, per handle, whether this line corrected it.
- **Colour comes from the source:** a clause of a regulation document gives red; a fact checked against what the host prompter shows gives orange. The compliance judge flags only what a regulation document says; there is no rule written in code. Both are the same size and stay until corrected.
- **No product-specific prompts or rules.** A product enters only through its documents: onboarding reads the uploaded PDFs with Gemini 3.8 Flash into a release, a Brief agent writes the prompter points and speech hints, and people only approve. Regulations are uploaded separately, as PDF.
- **Viewer comments** are answered from the product record when it answers them and sent to a person when it does not ([docs/comments.md](docs/comments.md)).

## Google Cloud

| Service | Use |
|---|---|
| Speech-to-Text V2, `chirp_3` (region `us`) | streaming transcription of the host, with phrase hints from the brief |
| Vertex AI Gemini 3.5 Flash-Lite (global endpoint) | live compliance judge and context judge, with a fixed seed |
| Vertex AI Gemini 3.8 Flash (global endpoint) | live fact checker and prompter judge; onboarding: reading product documents, the Brief agent |
| Agent Development Kit (ADK) | the AI PD, an `LlmAgent` that picks the next operator card (promo ending, shout-out) from checked candidates (`backend/app/agents/ai_pd.py`) |
| Cloud Run (us-central1, behind IAP) | the app: FastAPI backend, React screens, server-sent events; one instance (max-instances 1) with session affinity, so a show's live timers, event stream and audio socket stay in one process |
| Firestore (`live-studio`) | show state (sessions, transcripts, alerts, segments, events), written behind memory and read back after a restart |
| Cloud Storage | approved releases, briefs and regulation packs (write-once) |
| Model Armor | screening viewer comments |

## Evaluation

**Method**
- Each round uses a new sealed set of products with invented documents. The developer never sees it.
- GPT wrote the host lines and a first label for each; a separate Claude critic labelled the same lines blind. Every later label change is logged with its reason.
- Host lines are spoken by a Windows TTS voice and go through the real Chirp 3 path into the app, so speech-to-text errors count.
- Pass lines hold for every product, not on average: detection ≥ 95%, false alerts < 1%, no red alert on a non-regulation line, judge time ≤ 5 s (a soft target: a slower answer still shows, late).
- Contrived stress lines are reported apart from the natural lines.

**Set 10 in detail**: [docs/eval/sealed-set-10-results.md](docs/eval/sealed-set-10-results.md).
- Left out: 12 stress lines (one sentence cut into two audio clips on purpose) and 6 lines that need a fact not on the prompter or a rule outside the product's regulation document.
- Both misses in the main run are fact checks that never came back on a night when Gemini 3.8 Flash was slow.
- Alerts seen within 5 s of the line's end: 34 to 50 of 54, depending on the run. Most late alerts are fact checks.

**Earlier sealed sets** (detection on unseen products, older conditions, not comparable): 84% (set 3, typed text, 10/5) → 91.0% (set 4, typed text) → 89.6-90.3% (set 6, first round through TTS and STT) → 94.0% / 95.5% (set 7, 10/8: the fact checker read whole product documents and judge answers were dropped after 5 s).

**Code rules against model judges** (set 5, same STT lines, diagnostic because the set had been seen): code gates on top of the model gave 19.4% false alerts and 5 wrong strongest alerts; model verdicts alone gave 0.9-1.9% false alerts and 1 wrong strongest alert. This is why code no longer judges meaning.

## Known limits

- The fact checker (Gemini 3.8 Flash) is often slower than 5 s, and much slower on a busy Gemini day; its alerts then show late.
- Set 10 has 4 products and 54 violations, so one line moves detection by about 2 points.
- Tested with TTS voices, not yet with a real human host.
- Show state, comments included, is kept in Firestore and survives a restart or a move to a new instance.
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
