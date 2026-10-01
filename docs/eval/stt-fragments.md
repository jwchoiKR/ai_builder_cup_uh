# STT sentence fragments and compliance alerts · 2026-10-01

Question: chirp_3 with SHORT endpointing splits host sentences into several finals. How often is a short final followed by another final within 1 s, and can S07 or another compliance line be split so that an alert is missed or raised falsely?

**Sources:**
- the recorded voice rehearsals (`docs/rehearsal-script.json`, `docs/rehearsal-alerts.json`);
- a new experiment on real Speech-to-Text and Vertex AI (section 3).

## 1. Statistic from the rehearsal logs
**Setup:**
- 2 full-script runs plus the 10-sentence alert run.
- Synthetic SAPI voice (Zira), chirp_3 `us`, SHORT endpointing.
- Gaps are measured on `received_at` (and on `speech_end_at` in brackets).
- **Snapshot limit:** the state snapshot keeps only the last 20 finals with timestamps. The first 5 or 6 finals of each run have text only, and none of them is under 4 words, so the short-final count below is complete.

| | Run 1 | Run 2 | Alert run | Total |
|---|---|---|---|---|
| Finals | 25 | 26 | 10 | 61 |
| Finals under 4 words | 3 | 3 | 0 | 6 |
| … followed by another final within 1 s | 0 | 0 | 0 | **0** |
| Any two consecutive finals within 1 s | 0 / 19 | 0 / 19 | n/a | 0 |
| Smallest gap between consecutive finals | 1.75 s | 1.34 s | n/a | |

The short finals and what followed them:

| Short final | Next final | Gap |
|---|---|---|
| "Sorry, my mistake." (S06) | "The live price is $36." | 2.53 s (2.45 s) / 2.48 s (2.52 s) |
| "It's a moisturizer." (S08) | next host line | 26.2 s / 23.2 s |
| "Sorry, 4% Niacinamide." (S13) | none: last line of the run | n/a |

**Why the 1 s criterion never fires:**
- A continuation final can only arrive after the continuation itself has been spoken and endpointed (about 0.8 s).
- Real continuation gaps were 1.3–2.6 s here and 1.1–3.3 s in the experiment.
- A 1 s window therefore finds almost no fragments, including the dangerous one in section 3.

### Host sentences that came out as 2 or more finals
- **Rate:** run 1 split 5 of 20 sentences, run 2 split 6 of 20.
- **Where:** every split happened at a comma.
- **Alert run:** none of the 10 sentences was split.

| Scene | Sentence (split point ‖) | Runs | Effect |
|---|---|---|---|
| S02 | It's a lightweight gel-cream, ‖ so it absorbs really quickly. | 1, 2 | none: prompter point covered |
| S05 | Yes, it's a lightweight gel-cream, ‖ so just use a smaller amount on oily areas. | 1, 2 | none: judge linked the answer across both finals |
| S06 | Sorry, my mistake, ‖ the live price is thirty-six dollars. | 1, 2 | none: price note resolved |
| S08 | Just to be clear, ‖ it does not treat acne. | 1, 2 | Negation stayed with the claim ("It does not treat acne." / run 2 "Does not treat acne."). Reflex raised a provisional "treat acne" alert and the judge cleared it in both runs, so no host overlay. |
| S10 | …nobody reported a reaction, ‖ in our in-house test. | 2 | The qualifier became its own final. No rule is involved, so no alert either way. |
| S12 | It's a watery gel, ‖ just two to three drops after toner. | 1, 2 | none |

- **S07 in the logs:** one final in both runs, with the alert rendered at 2.86 s and 2.77 s.
- **Missed alerts and false overlays:** none in the logs.

## 2. Experiment
**What ran:**
- 11 compliance lines: S07 (two break points), S08/U13, U14, U17, U02, U03, U04, U07, U12 and U23.
- Each line was synthesized with SAPI (Zira, 16 kHz) with an SSML `<break>` of 0, 300, 500, 700 or 1000 ms inserted at the break point (‖ below).
- Each pause was run twice: 110 trials.

**How it ran:**
- Each trial used a fresh live session on a local backend with `LLM_PROVIDER=vertex`, `STT_PROVIDER=google_v2`, `JUDGE_MODE=split`, cream on air.
- Audio was streamed at real-time pace in 100 ms frames through `WS /api/sessions/{id}/audio`, followed by open-mic silence.
- So STT (chirp_3, SHORT, phrase hints), reflex, judge, fact checker and alert logic were exactly the app's.

**Outcome labels:**
- "Correct" means the expected rule was shown, or nothing was shown for a negated or quoted line.
- "False" means a compliance alert was shown for a negated line.

| Case | Line (‖ = inserted pause) | Expected | Split at ‖ | Outcome (10 trials) | Notes |
|---|---|---|---|---|---|
| S07-a | Use it every night, ‖ and your wrinkles will disappear overnight. | HIGH ageing | 8/10 (≥ 300 ms) | 10 correct | Alert on fragment 2 "And your wrinkles will disappear overnight.", 2.1–2.6 s after its speech end. |
| S07-b | Use it every night and your wrinkles ‖ will disappear overnight. | HIGH ageing | 4/10 (≥ 700 ms) | 10 correct | All 4 split trials raised **two** HIGH alerts: fragment 1 ("…every night in your wrinkles.") on its own, then fragment 2. |
| S08 (U13) | Just to be clear, it does not ‖ treat acne. It's a moisturiser. | none (negated) | 2/10 (1000 ms) | 8 correct, **2 false HIGH** | **0–700 ms:** "Just to be clear." / "Does not treat acne." → cleared. **1000 ms:** "does not" / "Treat acne." → the judge confirmed ASEAN-3-SKIN-ACNE on "Treat acne." although RECENT_TRANSCRIPT ended with "does not"; shown 2.2–2.4 s. |
| U14 | Someone asked ‖ if it cures eczema. No, it's a cosmetic… | none (quoted) | 2/10 (1000 ms) | 10 correct | "Someone asked." / "If it cures eczema." was cleared by the judge from context. |
| U17 | We can't say ‖ it removes wrinkles, but it helps… | none (negated) | 4/10 (≥ 700 ms) | 5 correct, **5 false** | **Split trials (4/4):** STT heard "**We can say.**", so the negation was lost by recognition, and the alert fired on "It removes wrinkles…". **Unsplit trial (1, 300 ms):** the judge flagged the full negated sentence. |
| U02 | This cream literally ‖ cures eczema. | HIGH disease | 8/10 | 10 correct | Fired on the fragment "cures eczema". |
| U03 | The ampoule treats acne, ‖ so you'll never break out again. | HIGH acne | 9/10 (also at 0 ms) | 10 correct | 9/10 raised two ACNE alerts, one per clause. |
| U04 | Once you use it, ‖ the results are permanent. | HIGH permanent | 8/10 | 10 correct | In 3 trials the judge also flagged "Once you use it." on its own (span "Once you use it"). |
| U07 | It's totally safe ‖ for pregnant women, don't worry. | HIGH vulnerable | 5/10 (≥ 500 ms) | 9 correct, 1 MEDIUM only | **Correct trials:** the reflex phrase "safe for pregnant" was split, but the judge still raised ASEAN-2D-VULNERABLE on "for pregnant women" from context. **Exception (1):** the rest of the sentence was not finalized inside the trial during the load window (below), so only BRAND-ABSOLUTE-SAFETY (MEDIUM) fired. |
| U12 | It kills ‖ the bacteria on your skin. | HIGH antimicrobial | 6/10 (≥ 500 ms) | 9 correct, **1 missed** | Judge-only claim: reflex "kills bacteria" does not match "kills the bacteria". 5 of the 6 split trials raised two alerts. **The miss:** a judge timeout in the load window, with no reflex hit to fall back on (§8.4.3). |
| U23 | It's a hundred ml tube, ‖ so it lasts forever. | HIGH permanent | 8/10 | 10 correct | Fired on "So it lasts forever." |

**Split rate at the inserted pause:**

| Pause | 0 ms | 300 ms | 500 ms | 700 ms | 1000 ms |
|---|---|---|---|---|---|
| Split at ‖ | 2/22 | 10/22 | 14/22 | 17/22 | 21/22 |

**Totals:**
- **Alert expected (80 trials):** 78 raised the expected rule, 1 missed, 1 raised only a MEDIUM rule.
- **No alert expected (30 trials):** 23 correct, 7 false: S08 ×2 (negation separated from the claim) and U17 ×5 (4 with the negation lost by STT, 1 judge error).
- **Duplicates:** 21 of the 80 alert trials showed more than one HIGH alert for one spoken claim.

**Latency (expected rule, measured from the speech end of the final that raised it):**
- Unsplit: p50 2.52 s, p95 3.50 s (n 23).
- Split: p50 2.33 s, p95 3.64 s (n 55).
- Splitting does not slow the alert, because the claim-bearing fragment is judged as soon as it is final.

**Load caveat:**
- Between +80 s and +200 s of the 410 s run, a separate STT harness kept 4 more streams open.
- In that window, 7 trials had STT lags of 1.7–18.5 s.
- Outside it, STT lag was p95 1.0 s and max 1.66 s.
- The U12 miss, the U07 MEDIUM-only trial and the latency outliers (6.6 s, 20 s) all fall in that window.
- The S08 false alerts do not: normal STT lag, no judge timeout.

**Fragment statistic in the experiment:**
- 217 finals, 60 of them under 4 words.
- 2 were followed by another final within 1 s, both in one trial inside the load window, where STT released three finals together.
- Gap between consecutive finals: p50 2.16 s, min otherwise 1.07 s.

### SHORT vs STANDARD endpointing (STT only, 13 split-prone configs × 2)
| | SHORT | STANDARD |
|---|---|---|
| Finals per line | 2.5 | 1.8 |
| Kept together by STANDARD | n/a | S08 at 0 and 700 ms (comma), U04 300 ms, U12 500 ms, U14 1000 ms |
| Split in both modes | | S07-a 500 and 1000 ms, S07-b 700 and 1000 ms, U07 1000 ms, U12 1000 ms |
| **S08 at 1000 ms** | "Just to be clear." / "It does not." / "Treat acne." | "Just to be clear, it does not." / "**Treat acne.**" (2/2) |

**Notes:**
- **Latency:** this harness opened a new client per stream, so its latencies are not comparable. The VERIFIED §4.10 probe gives STANDARD finals about 0.4–0.5 s later.
- **Punctuation:** it does not reliably mark a fragment. The same audio gave "does not" through the app and "It does not." in this harness.

## 3. Answers
- **Short finals followed by another within 1 s:** 0 of 6 in the rehearsals, and 2 of 60 in the experiment (one STT stall). The 1 s criterion is too narrow to detect fragments: continuations arrive 1.1–3.3 s later.
- **S07 can be split:**
  - at the comma after "night" with a pause of 300 ms or more (8/8);
  - inside the claim with 700 ms or more (4/4).
  - **Outcome:** the alert was still correct 20/20, at 2.1–2.6 s after the speech end of the fragment.
  - **Side effect:** the inside-claim split raised **two HIGH alerts** for one claim. `apply_corrections` resolves only the listed alerts and the alerts of the same transcript, so a correction must list both.
- **Negated compliance lines can be split into a false HIGH alert:**
  - S08 with a 1 s pause after "does not" (2/2);
  - U17 with 0.7 s or more after "can't say" (4/4, where STT also turned "can't" into "can").
- **Judge timeout path:** with a judge timeout on such a fragment, §8.4.3 "fail toward warning" would raise an unverified HIGH alert even if the judge would have cleared it. Reflex sees no negation inside "Treat acne." alone.
- **Quoted lines (U14):** handled correctly when split.

## 4. Proposed fix
**Status:** option B was implemented as D-088, with the reviewer's rules.
- **Merge trigger:** a merge happens only when the previous final does not end with `.`, `?` or `!`, instead of the looser test below.
- **Dedupe:** a rule already active from the merged fragments gets no second alert.
- **Not re-measured yet:** the acceptance check at the end of this section was not re-run with real STT. The human microphone rehearsal is next.

The proposal as written before implementation:
| Option | Change | Latency cost on the S07 alert | What it fixes here | Risks |
|---|---|---|---|---|
| **A. Hold and join** | Hold a final that looks incomplete (under 4 words, no terminal punctuation, or ending in a negation or quote cue) until the next final or N ms; judge the joined text. | 0 when S07 arrives as one complete final. The hold must be N ≈ 2.5–3 s to catch continuations (1 s would have joined none), and a claim-bearing fragment with no continuation waits the full N: U02 "cures eczema" (no period) would go from 2.2 s to about 4.7–5.2 s, at or over the 5 s p95 budget. | S08 at 1000 ms; duplicate alerts | Delays real alerts. Punctuation is an unreliable signal. Ordering gets harder in the transcript chain. |
| **B. Context window, no hold (recommended)** | Process every final at once as today, but run reflex and the judge on "previous final + current final" instead of the current final alone, when **both** hold: the previous final arrived ≤ 3.5 s earlier, **and** the pair looks like one sentence (previous final under 4 words, without terminal punctuation, or ending in a negation or quote cue; or current final starting lowercase or under 4 words). Remove the boundary period before the reflex scan. Never create a second active alert for a rule already active on the previous final; widen the correction instead. | **0 s** (no waiting; about 10 more judge input tokens). S07 stays at p50 ≈ 2.5 s (rehearsal render 2.77–2.86 s). | **S08:** the window "…it does not treat acne" is the input that was cleared 8/8 in the 0–700 ms trials and 2/2 in the rehearsals. **Judge-timeout fallback:** the reflex hit is negated, so no unverified HIGH alert. **Duplicates:** the double HIGH alerts on one claim (21/80 trials) and fragment spans like "Once you use it". | The window can pair unrelated sentences, so a "not" at the end of the previous final could mask a new claim. Keep the judge as the decider, and limit cross-boundary negation to cues in the last 4 tokens of the previous final. Does not fix STT errors (U17 "can't" → "can"). Needs a decision record and a re-run of this experiment. |
| C. STANDARD endpointing | `ENDPOINTING_SENSITIVITY_STANDARD` | +0.4–0.5 s on every final, so S07 at about 3.0 s p50 and 3.8 s p95 | Fewer splits at 300–700 ms pauses | **Does not fix S08 at 1000 ms** (2/2 still "…it does not." / "Treat acne."). Every final gets slower. |
| D. Prompt only | Tell the judge to read UTTERANCE as a continuation of RECENT_TRANSCRIPT's last line | 0 s | Uncertain: the judge already had "does not" in RECENT_TRANSCRIPT and flagged "Treat acne." 2/2 | Prompts are data-pack files. It does not cover the reflex fallback. |

**Recommendation: B, keeping SHORT endpointing.**

**Acceptance check before the human rehearsal:** re-run this experiment and require:
- 0 false alerts for S08 at 700–1000 ms;
- no second HIGH alert for one claim (S07-b, U12, U03);
- S07 alert p50 unchanged at about 2.5 s.

**Separate from fragmenting (not fixed by any option):**
- A pause after "can't" made chirp_3 hear "can" (U17, 4/4 at 700 ms or more).
- The judge once flagged the unsplit negated U17 sentence (1/10).

Both need checking with a human voice in the §14.5 microphone rehearsal, because SAPI pauses are artificial.
