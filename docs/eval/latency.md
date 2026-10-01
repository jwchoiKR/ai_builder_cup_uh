# Latency report · 2026-10-01

**Sources:** all measurements are real Vertex AI and Speech-to-Text calls, project `separk-cloocus`, from:
- `docs/eval/2026-10-01-split.md` (30 runs);
- `-single.md`;
- `-comments-5runs.md`;
- `composer-thinking.md`;
- `docs/rehearsal.md` (voice rehearsals).

## Against the speed budget (DEV_SPEC §3.7)

| Budget | Target | Measured | Status |
|---|---|---|---|
| Speech end → compliance alert visible on host | ≤ 5 s p95 | p95 **3.3 s** (10 HIGH alerts, synthetic voice, real STT and models); S07 in the full-script runs 2.86 s and 2.77 s | met |
| Comment received → visible in chat | ≤ 300 ms | `comment.created` is emitted inside the intake request, before any LLM step (§8.8 step 1; prefilter < 1 ms). Browser paint time was not measured separately. | met on the server side |
| Cached auto answer | ≤ 1 s | Answer-cache hits publish without a composer call. Comment → reply still includes triage: median 1.3 s (run 1) and 2.0 s (run 2). Only a triage-cache hit (same normalised text) is instant. | **not met** unless the triage cache hits (see note) |
| First-time auto answer | ≤ 15 s (best effort) | composed replies: median 3.4 s; composer p50 2.0–2.4 s, p95 3.0–8.0 s (LOW thinking) | met |

**Note on cached answers.** §8.8 requires triage before grouping, because the cache lookup needs the group or key. Triage on `gemini-3.5-flash-lite` (MINIMAL) has p50 1.28–1.38 s over 5 runs. A cached answer therefore reaches a new asker in about one triage call. Meeting ≤ 1 s would need one of:
- a faster triage model;
- deterministic pre-routing of near-duplicate comments.

Both are outside the v1 spec, so this is left as a known gap.

## Agents

| Agent | Model · thinking | Deadline | p50 | p95 | max | n | Non-ok |
|---|---|---|---|---|---|---|---|
| UtteranceJudge (split) | 3.5-flash-lite · MINIMAL | 2.5 s | 1.37 s | 1.65 s | 2.48 s | 1170 | 0 |
| FactChecker | 3.5-flash-lite · MINIMAL | 3.0 s | 1.15 s | 1.62 s | 2.83 s | 1169 | 1 timeout |
| Judge (single mode, for comparison) | 3.5-flash-lite · MINIMAL | 2.5 s | 1.73 s | 2.06 s | 2.41 s | 195 | 0 |
| CommentTriage | 3.5-flash-lite · MINIMAL | 2.5 s | 1.28–1.38 s | 1.37–1.60 s | – | 5 × 35 | 0 |
| AnswerComposer | 3.8-flash · LOW (`COMPOSER_THINKING`) | 12 s | 2.0 s | 3.0 s | 7.9 s | 75 (run A) | 0 |
| AnswerComposer | 3.8-flash · MEDIUM (for comparison) | 12 s | 5.3 s | 10.3 s | 14.8 s | 75 (run A) | 1 timeout |
| BriefAgent | 3.8-flash · MEDIUM | 60 s | cream 22.5 s, ampoule 12.7 s (one run each) | | | 2 | 0 |
| BroadcastSummary | 3.8-flash · MEDIUM | 30 s | within the deadline in both rehearsals | | | 2 | 0 |

## Speech-to-Text (chirp_3, `us`, SHORT endpointing)

| Measure | Value |
|---|---|
| Speech end → final transcript (10 alert sentences) | p50 0.88 s, max 1.40 s |
| Speech end → final transcript (full script, 25 + 26 finals) | p50 0.88 s, p95 1.04 s / 1.69 s |
| SHORT vs STANDARD endpointing (probe) | final about 0.4–0.5 s earlier with SHORT |
| Interim results | none returned by chirp_3 |

## Notes
- **Timeouts.** Run-to-run variance is real. A composer run made while the project was also running rehearsals and E2E showed longer tails and three timeouts on LOW: `composer-thinking.md` run B. Model warm-up at start (§7.1) removes the cold first call, which took 3–32 s in P0 probes.
- **X-Server-Timeout header.** It is not sent (D-047). With it, Vertex returned early 504s on the judge. Without it, the judge had 0 timeouts in 1,170 calls.
