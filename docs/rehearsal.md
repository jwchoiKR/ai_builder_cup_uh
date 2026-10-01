# Rehearsal (DEV_SPEC §14.3 latency check, §14.5)

**Date and setup:**
- Recorded 2026-10-01.
- Backend with `LLM_PROVIDER=vertex` (gemini-3.5-flash-lite / gemini-3.8-flash, `COMPOSER_THINKING=LOW`) and `STT_PROVIDER=google_v2` (chirp_3, `us`, `en-US`, SHORT endpointing, glossary phrase hints).
- Project `separk-cloocus`.

**How the audio was produced.** No person spoke for these runs.
- Each host line was synthesized with Windows SAPI ("Microsoft Zira Desktop", en-US) to 16 kHz mono PCM.
- It was streamed at real-time pace in 100 ms frames, with silence between lines (like an open microphone), through the same `WS /api/sessions/{id}/audio` the browser microphone uses.
- So speech-to-text, the utterance pipeline, the models and the host page (open in Edge, sending render acknowledgements) were all real. Only the voice was synthetic.
- Driver: `frontend/e2e/rehearsal-voice.mjs`. Raw data: `docs/rehearsal-alerts.json`, `docs/rehearsal-script.json`.

> **Still to do with a person:** the §14.5 rehearsal with a real microphone and a human voice (full script twice). In `/studio`, press **D**, then Mic **Start** (or **M** on the host screen), and read `data/demo/host_script.md`. Then copy `GET /api/sessions/{id}/metrics` into this file.

## 1. Ten HIGH-risk sentences (P4 "done when": speech end → host render ≤ 5 s p95)
Each alert was dismissed before the next sentence, so every alert mounted the overlay and sent its own render acknowledgement.

| # | Spoken line | STT final | Rule | STT ms | shown ms | rendered ms |
|---|---|---|---|---|---|---|
| 1 | Use it every night and your wrinkles will disappear overnight. | same | ASEAN-3-SKIN-AGEING | 1403 | 2866 | 2890 |
| 2 | This cream literally cures eczema. | same | ASEAN-2D-DISEASE | 1002 | 2474 | 2486 |
| 3 | The ampoule treats acne, so you'll never break out again. | same | ASEAN-3-SKIN-ACNE | 889 | 2626 | 2639 |
| 4 | Once you use it, the results are permanent. | same | ASEAN-2E-PERMANENT | 866 | 2596 | 2608 |
| 5 | It regenerates your skin cells from the inside. | same | ASEAN-DP5-PHYSIOLOGICAL | 798 | 2368 | 2375 |
| 6 | It even removes your old acne scars. | same | ASEAN-3-SKIN-SCARS | 780 | 3267 | 3286 |
| 7 | It's totally safe for pregnant women, don't worry. | same | ASEAN-2D-VULNERABLE | 934 | 2800 | 2813 |
| 8 | You'll look ten years younger after one bottle. | "…10 years younger…" | ASEAN-3-SKIN-AGEING | 877 | 2772 | 2786 |
| 9 | It kills the bacteria on your skin. | same | ASEAN-3-SKIN-ANTIMICROBIAL | 891 | 2671 | 2685 |
| 10 | It's a hundred ml tube, so it lasts forever. | "…100 ml…" | ASEAN-2E-PERMANENT | 865 | 2816 | 2828 |

**Column meanings:** "STT ms" is speech end → final transcript; "shown ms" is speech end → alert active; "rendered ms" is speech end → host overlay mounted.

**Result:**
- 10/10 alerts were raised with the correct rule at HIGH severity.
- Speech end → host render: p50 2.7 s, p95 **3.3 s**, max 3.3 s, against the 5 s target. **PASS.**
- Speech-to-text alone: p50 0.88 s, max 1.40 s.

## 2. Full demo script, twice
The full `host_script.md` ran in order:
- host lines by synthetic voice;
- bursts B1–B5, the time sale and the end through the API;
- background chatter off.

| Scene | Expected | Run 1 | Run 2 |
|---|---|---|---|
| S02 | cr-p1, cr-p2 covered | ✓ | ✓ |
| S03–S04 | price group (4 askers) answered once; oily 7, makeup 4 | ✓ | ✓ |
| S05 | host answer posted to the oily-skin askers | ✓ (judge linked the answer across the split final "Yes, it's a lightweight gel cream." / "So, just use a smaller amount on oily areas.") | ✓ |
| S06 | price note S$32 → S$36.00, then corrected | shown 2.65 s, corrected 10.1 s | shown 2.65 s, corrected 9.2 s (STT heard "life price"; still resolved) |
| S07 | HIGH alert ≤ 5 s, then corrected | rendered **2.86 s**, corrected in 7.2 s by "Let me correct that." | rendered **2.77 s**, corrected in 6.1 s |
| S08 | no full-screen alert | provisional "treat acne" cleared | cleared |
| S10 | 3 / 3 required points | ✓ | ✓ |
| S11 | promo prices answered | ✓ | ✓ |
| S12 | two cues → switch to the ampoule | ✓ | ✓ |
| S13 | 10% → 4% niacinamide note, then corrected | shown 2.70 s, corrected 8.6 s | shown 2.83 s, corrected 7.6 s |
| S14 | summary with AI recap | ✓ | ✓ (`docs/screens/S14-summary.png`) |

Metrics from `GET /api/sessions/{id}/metrics` at the end of each run:

| Metric | Run 1 | Run 2 |
|---|---|---|
| STT final latency p50 / p95 (n) | 0.88 / 1.04 s (25) | 0.88 / 1.69 s (26) |
| Judge p50 / p95 (ok / timeout) | 1.52 / 1.83 s (25 / 0) | 1.57 / 1.81 s (25 / 1) |
| Fact checker p50 / p95 (ok / timeout) | 1.32 / 1.70 s (25 / 0) | 1.31 / 1.48 s (25 / 1) |
| Comment triage p50 / p95 (ok / timeout) | 1.37 / 1.61 s (37 / 0) | 1.38 / 1.98 s (36 / 1) |
| Answer composer p50 / p95 | 2.05 / 5.46 s | 2.38 / 8.03 s |
| Answers instant / composed; median reply | 5 / 9; 1.3 s / 3.4 s | 3 / 11; 2.0 s / 3.4 s |

**Observations:**
- **Sentence splitting.** chirp_3 with SHORT endpointing splits longer host sentences at pauses into two or three finals, e.g. "Let me correct that." / "It helps keep your skin hydrated…". The judge still handled corrections and answers correctly, because it gets the previous two finals as context (§7.3).
- **Interim results.** chirp_3 returned none, so the operator's interim transcript line stays empty (VERIFIED §4.10).
- **Timeouts.** Run 2 had one timeout each for the judge, the fact checker and triage, with Vertex tail latency at the time. No alert was missed, because S06, S07 and S13 were not affected.
- **Vertex screenshot.** An operator screenshot from run 2, taken after S07, shows the measured header chips: `docs/screens/vertex-operator-metrics.png` ("Alert in 2.8s", "Judge p50 1.6s").
