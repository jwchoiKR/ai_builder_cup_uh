# Scene screenshots (phase P3)

**How they were made** (`npm run capture`, script `frontend/e2e/capture-scenes.mjs`):
- Captured on 2026-10-01 at 1920×1080.
- `/studio?layout=all` shows the Host, Operator and Viewer panes side by side.
- The backend ran with `LLM_PROVIDER=mock` and `STT_PROVIDER=mock`, replaying the agent outputs recorded from Vertex AI (`backend/tests/fixtures/llm/`).
- Host lines were injected as final transcripts. Bursts B1–B5 and the time sale were fired through the API, in the order of `data/demo/host_script.md`.
- At each shot the driver waited for the scene's expected on-screen text (copy deck §12.9). All 22 texts were found.

**How to reproduce:**
1. Run `npm run build` in `frontend/`.
2. Start the backend with mock providers:
   ```sh
   LLM_PROVIDER=mock STT_PROVIDER=mock uv run uvicorn app.main:create_app --factory --port 8000
   ```
3. Run `npm run capture` in `frontend/`. It uses the installed Microsoft Edge; set `PW_CHANNEL=chrome` for Chrome.

| File | Scene | What it shows (host_script "Expected") |
|---|---|---|
| S02-start.png | S02 | LIVE timer, Now = Hydra Barrier Cream, Next = Deep Hydration Ampoule, cream prompter; operator run of show "On air now". |
| S02-points.png | S02 | cr-p1 and cr-p2 grey with checks; required counter 1 / 3. |
| S03-price-questions.png | S03 | Reactions without reply; one price group with one "AI answer" (S$36.00) to all askers; set price S$62.00. |
| S04-grouping.png | S04 | Oily-skin group (7 askers) and makeup (4); host top 3 with suggested answers; fragrance auto-answered. |
| S05-posting.png | S05 | "Posting answer…" chip on the oily-skin card. |
| S05-host-answer.png | S05 | Card left the top 3; viewer shows the "Host answer" reply under Raj's question. |
| S06-fact-error.png | S06 | Amber "Price correction ✕ S$32 → ○ S$36.00" on host with source; amber card on operator. |
| S06-corrected.png | S06 | Correction bar cleared on both screens. |
| S07-compliance.png | S07 | Full-screen red alert: "Say this instead", the spoken phrase, rule and source; operator "Host correction required". |
| S07-not-corrected.png | S07 | After 5 s: operator card "Not corrected · mm:ss". |
| S07-corrected.png | S07 | Green "Corrected" bar on host; operator card "Corrected in N.N s"; cr-p3 grey. |
| S08-negation.png | S08 | No full-screen alert after the negated sentence. |
| S09-sensitive.png | S09 | Pregnancy, eczema and shipping questions only on the operator desk as "Needs review"; spam, link, phone and harassment hidden. |
| S10-points.png | S10 | cr-p4 grey; 3 / 3 required points. |
| S11-time-sale.png | S11 | Viewer time-sale pop-up with 10:00 countdown; host TIME SALE chip; promo prices. |
| S11-promo-answers.png | S11 | "how much is the cream now?" answered with S$32.40; set S$55.80. |
| S12-cue-1.png | S12 | First switch cue; operator transcript chip "switch cue 1/2"; am-p1 pre-covered. |
| S12-switching.png | S12 | Green "Switching to Deep Hydration Ampoule" countdown with "Cancel switch (Esc)"; operator "Switching in Ns". |
| S12-switched.png | S12 | Now = Deep Hydration Ampoule, Next = End of run sheet; am-p1 and am-p2 grey; cream questions off the host top 3. |
| S12-b5.png | S12 | B5 after the switch: "how much?" attributed to the cream (grace window), ampoule questions to the ampoule; "Does the ampoule sting?" in Needs review. |
| S13-fact-error.png | S13 | "Ingredient amount correction ✕ 10% niacinamide → ○ 4% niacinamide". |
| S13-corrected.png | S13 | Bar cleared. |
| full-host-S04-questions.png | S04 | Host screen alone at 1920×1080 with the top 3 audience questions. |
| full-host-S07-compliance.png | S07 | Host full-screen compliance alert at 1920×1080. |
| full-host-S12-switching.png | S12 | Host switch countdown at 1920×1080. |
| full-operator-S09-desk.png | S09 | Operator control room at 1920×1080: question desk, run of show, live transcript with agent chips. |
| full-viewer-S11-time-sale.png | S11 | Viewer phone page with the time-sale pop-up. |

**Updates after review:**
- The UI fixes of the screenshot review (D-072–D-078) are in all scene shots above, re-captured on 2026-10-01. Visible fixes:
  - the red frame on the HIGH overlay;
  - desk counts that match the tabs;
  - set label for set-price groups;
  - "Source: active promotion";
  - "Also answered: @Name".

**Real models (P4/P5):** backend with Vertex AI and Speech-to-Text; host lines spoken with a synthetic voice (`docs/rehearsal.md`).

| File | Scene | What it shows |
|---|---|---|
| S01-setup-documents.png | S01 | Both shipped PDFs listed as "Indexed locally". |
| S01-setup-brief.png | S01 | Brief Agent results for both products: glossary tables and prompter point drafts. |
| S01-setup-confirmed.png | S01 | "Confirmed · version 1" after Confirm glossary. |
| S14-summary.png | S14 | Summary of a full voice rehearsal. Per-product cards, unanswered questions, compliance and fact logs with correction times, promotions, agent latency, AI recap built only from the numbers shown. |
| vertex-operator-metrics.png | S07 | Operator during a Vertex run, after S07: "Alert in 2.8s", "Judge p50 1.6s" (measured values), live transcript with agent chips. |
