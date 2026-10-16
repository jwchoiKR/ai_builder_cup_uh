# LIVE / Studio

**A real-time compliance and fact co-pilot for live-commerce hosts, on Google Cloud.**

AI Builder Cup 2026 · Track: Retail & Commerce

## Summary

1. **Problem:** A live-commerce host talks unscripted for an hour, and one claim the regulations prohibit ("it cures eczema") or one wrong price can break the rules on air. Today a producer or a compliance checker has to catch it by ear.
2. **User and workflow:** Before the show an operator uploads the product PDF and the regulation PDFs, and approves what the AI read. On air the host only talks: the host screen shows a red or orange box with a line to say instead, clears it when the host corrects it in their own words, ticks the prompter and lists viewer questions with answers. An operator can watch from a control room, but a solo host can run without one. After the show an AI recap is built from the show's numbers.
3. **What is different:** Gemini judges the meaning of every line, and code never drops or rewrites a verdict. There are no product-specific prompts or rules: a new product enters only through its documents. The host never touches the screen.
4. **Measured:** On a sealed set of 4 products the app had never seen, 162 natural host lines went through the real Chirp 3 speech-to-text path: 96.3% detection, 0% false alerts, no red alert on a line without a regulation problem, compliance judge p95 2.9 s. The fact checker's p95 was 4.5 s on a 10/16 show (36 calls), inside its 7 s target; on a slow Gemini night during set 10 it reached 31.5 s.
5. **Cost:** the judges and speech-to-text cost about US$3.8 an hour at 600 host lines an hour ([Cost](#cost)).
6. **Limits:** The alerts help the host; they do not guarantee compliance. Only the uploaded regulations are checked, a person approves every product before air, and the tests used TTS voices, not yet a real host.

## Evidence at a glance

Measured on a sealed set of 4 products the app had never seen (set 10, 10/14-15), 162 natural host lines in English and Korean, spoken by a TTS voice through the real Chirp 3 speech-to-text path, on the current judge setting:

| | Result | Pass line |
|---|---|---|
| Detection of prohibited claims and wrong facts | **96.3%** (52 of 54) | ≥ 95% |
| False alerts on safe lines | **0%** (0 of 108) | < 1% |
| Red (regulation) alert on a line without a regulation problem | **0** | 0 |
| Compliance judge, one call p50 / p95 | **1.4 / 2.9 s** | ≤ 5 s |
| Fact checker, one call p95 | **4.5 s** (10/16 show, 36 calls); set 10: p50 6.0 / p95 31.5 s on a slow Gemini night (504s) | ≤ 7 s |

- Three more runs on the same set with other compliance settings, on a normal Gemini day: 100% detection and 0-0.9% false alerts each.
- Per product, per line (ids and outcomes, no sealed text), alert times and the conditions: [docs/eval/sealed-set-10-results.md](docs/eval/sealed-set-10-results.md).
- The set itself (product documents, host lines, labels, raw results) and the script that rebuilds these numbers: [eval/sealed_set_10](eval/sealed_set_10/README.md).

## What happens on air

| The host says | The host screen shows |
|---|---|
| "Use it every night and your wrinkles will disappear overnight." | Red **Regulation** box: the claim, the clause of the regulation PDF it breaks, and a compliant line built only from the product's approved claims. It clears when the host corrects it, in any words. |
| "The live price is S$32 today." (the product sheet says S$36) | Orange **Product info** box: "Cream: The live price is S$36.00". It clears when the host says the right value. |
| "Now let me show you the toner." | The prompter moves to the next product in the run sheet at once. The operator can undo it. |
| A prompter point, said in any words | The point is ticked on the prompter. |

## How it works

```
viewer comments ─▶ comment path (Model Armor screen, triage, answer from the product's document, or send to a person)

host mic ─▶ Chirp 3 streaming STT (speech terms from the product record as hints)
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
- **No product-specific prompts or rules.** A product enters only through its PDF: Gemini 3.8 Flash reads it into a product record (brand, category, every priced option, prompter points, speech terms), and a person only approves it. Regulations are uploaded separately, as PDF.
- **Viewer comments:** spam, abuse and prompt attacks are hidden (Model Armor). A product question is answered from the product's own document (Vertex AI Search) and marked "AI answer". Questions the document does not answer, and health, claim and test-result questions, wait for the host or the operator with a suggested reply ([docs/comments.md](docs/comments.md)). On the viewer page, chatters appear as animal characters.

## Google Cloud

| Service | Use |
|---|---|
| Speech-to-Text V2, `chirp_3` (region `us`) | streaming transcription of the host, with speech terms from the product record as hints |
| Vertex AI Gemini 3.5 Flash-Lite (global endpoint) | live compliance judge and context judge, with a fixed seed |
| Vertex AI Gemini 3.8 Flash (global endpoint) | live fact checker and prompter judge; reading product PDFs; comment triage, answers, recap |
| Agent Development Kit (ADK) | the AI PD, an `LlmAgent` that picks the next operator card (promo ending, shout-out) from checked candidates (`backend/app/agents/ai_pd.py`) |
| Cloud Run (us-central1) | the app: FastAPI backend, React screens, server-sent events; autoscaling up to 3 instances with session affinity |
| Firestore (`live-studio`) | show state (sessions, transcripts, alerts, segments, events), written behind memory and read back after a restart |
| Cloud Storage | approved releases, briefs and regulation packs (write-once) |
| Vertex AI Search | finds the asked product's passages behind a viewer answer |
| Model Armor | screens viewer comments for spam, abuse and prompt attacks |

## Why Gemini 3.5 Flash-Lite and Gemini 3.8 Flash

Each judge runs on the model that did best on its own job in our tests. An alert should show within 5 s of the line's end, so speed comes first for the alerts the host must see at once.

**Gemini 3.5 Flash-Lite: compliance judge and context judge**
- A regulation alert has to be fast. One compliance call took 1.4 s at p50 and 2.9 s at p95 on set 10.
- The compliance judge thinks at LOW with a fixed seed, so the same line gets the same verdict on another run.
- The context judge (product switch, which viewer question was answered) thinks at MINIMAL, so the prompter moves as soon as the host names the next product.
- We tried Gemini 3.8 Flash as a second check on every alert (10/6). It cut false alerts, but one call took 3.6 s on average and 8.7 s at p95, too slow for a 5 s alert.

**Gemini 3.8 Flash: fact checker and prompter judge**
- The fact checker must tell a wrong value from the same value said another way or a claim the host only reports. On 336 lines of sealed set 8, 3.8 Flash gave 2 false fact alerts and Flash-Lite 11, with the same detection.
- The cost is time: its p95 reached 31.5 s on a slow Gemini night (see Known limits). A late fact alert still shows.
- The prompter judge ticks a point only when the host has said all of it. In a 5-run probe, Flash-Lite ticked 11 of 38 points the host had not fully said; 3.8 Flash ticked 0 of 40 and missed none. Nothing waits on this judge, so its 2.2 s average does not delay any alert.

## Evaluation

**Method**
- Each round uses a new sealed set of products with invented documents. The developer never sees it.
- GPT wrote the host lines and a first label for each; a separate Claude critic labelled the same lines blind. Every later label change is logged with its reason.
- Host lines are spoken by a Windows TTS voice and go through the real Chirp 3 path into the app, so speech-to-text errors count.
- Pass lines hold for every product, not on average: detection ≥ 95%, false alerts < 1%, no red alert on a non-regulation line, judge time ≤ 5 s for the compliance judge and ≤ 7 s for the fact checker (soft targets: a slower answer still shows, late).
- Contrived stress lines are reported apart from the natural lines.

**Set 10 in detail**: [docs/eval/sealed-set-10-results.md](docs/eval/sealed-set-10-results.md).
- Left out: 12 stress lines (one sentence cut into two audio clips on purpose) and 6 lines that need a fact not on the prompter or a rule outside the product's regulation document.
- Both misses in the main run are fact checks that never came back on a night when Gemini 3.8 Flash was slow.
- Alerts seen within 5 s of the line's end: 34 to 50 of 54, depending on the run. Most late alerts are fact checks.

**Earlier sealed sets** (detection on unseen products, older conditions, not comparable): 84% (set 3, typed text, 10/5) → 91.0% (set 4, typed text) → 89.6-90.3% (set 6, first round through TTS and STT) → 94.0% / 95.5% (set 7, 10/8: the fact checker read whole product documents and judge answers were dropped after 5 s).

**Other measured parts**

| Test | Result |
|---|---|
| Prompter judge, partial vs full points (10/11 probe) | wrong ticks 0 of 40, missed 0 of 63 |
| Product switch on a category word only | 0 of 5 without the category, 4 of 4 with it |
| Viewer comments: question / reaction / hide (233) | 99.6% |
| Comments: auto vs needs a person, as labelled | 90.6% · replies to prompt injections 0 |
| Onboarding read: 12 complete English product PDFs (new fictional brands), 3 reads each, current version (10/17); a Claude critic checked every point against the PDF, GPT re-checked each error | wrong prices 0 of 69 · invented claims 0 · reads with no critical error 34 of 36 (the 2 errors dropped part of a test result's conditions) |

**Code rules against model judges** (set 5, same STT lines, diagnostic because the set had been seen): code gates on top of the model gave 19.4% false alerts and 5 wrong strongest alerts; model verdicts alone gave 0.9-1.9% false alerts and 1 wrong strongest alert. This is why code no longer judges meaning.

## Cost

Judges and speech-to-text: about **US$3.8 an hour** at 600 host lines an hour.

| Item | Basis (measured) | Per line | Per hour |
|---|---|---|---|
| Compliance judge | Flash-Lite, ~14.0k tokens (regulation PDFs), 96% cached | $0.0007 | $0.39 |
| Context judge | Flash-Lite, ~4.3k tokens in | $0.0016 | $0.98 |
| Prompter judge | 3.8 Flash, ~1.6k tokens in, low thinking | $0.0013 | $0.78 |
| Fact checker | 3.8 Flash, ~5.5k tokens, 85% cached | $0.0011 | $0.65 |
| Speech-to-Text | chirp_3, $0.016 per audio minute | | $0.96 |

- Token counts of all 144 judge calls in one show on the deployed app (10/16, 36 host lines through Chirp 3), from Firestore, times Google's list prices (Gemini checked 10/17, Speech-to-Text 10/11). 600 lines an hour (10 a minute) is an assumption, not measured.
- Other AI steps (server logs 10/14-10/17): reading a product PDF $0.007, sorting a viewer comment $0.006, writing an AI answer $0.003, recap and comment insights $0.014 a show.
- Not counted: Vertex AI Search, Model Armor, repeat requests, cache storage (~$0.02 an hour), Cloud Run, Firestore.

## Next (planned, not built)

- Provisioned Throughput: reserved Gemini capacity under an SLA, so shared-capacity 429s (seen in tests) stop.
- Accept product documents beyond PDF (Word, slides, web pages, images), read the same way.
- Copy AI-call logs to BigQuery for analysis across shows.

## Known limits

- The fact checker (Gemini 3.8 Flash) can be slower than its 7 s target, much slower on a busy Gemini day; its alerts then show late.
- Set 10 has 4 products and 54 violations, so one line moves detection by about 2 points.
- Tested with TTS voices, not yet with a real human host.
- Show state, comments included, is kept in Firestore and survives a restart or a move to a new instance.

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

Deploy: `bash deploy/cloudrun.sh` (Cloud Run, Firestore database, bucket).

## Tests

```sh
cd backend && uv run pytest -q     # unit, pipeline and API tests with mock providers
cd frontend && npm test            # component and store tests
cd frontend && npm run e2e         # Playwright scenes
```
