# Live demo on the real models · 2026-10-03

Scenes S02–S14 of `data/demo/host_script.md` on `/studio`, against Vertex AI (`JUDGE_MODE=split3`, D-099). The session is `ses_01M3YMPFTPNH5Z91C8WA3FRJCQ`.

- **How it ran:** host lines were injected from the Demo Console as final transcripts (the same pipeline as speech-to-text). Comment bursts were fired from the console, and operator actions were clicked in the Operator pane.
- **Script:** a headed Playwright run with captions (not in the repo). It took 3 min 38 s.
- **Video:** `demo.mp4` (3 min 45 s, Korean captions at the bottom).
- **Layout:** Host + Operator. The Reset demo dropped `?layout=all`, so the viewer pane is not in these shots.
- **Viewer-side results:** these were checked in the session state instead:
  - the brand answer with the operator's edit was published;
  - the time sale started;
  - the S$32.40 and S$55.80 AI answers were published.

| File | Scene | What it shows | Seconds after the line |
|---|---|---|---|
| `01-S02-prompter.png` | S02 | Prompter points cr-p1 and cr-p2 said | 1.3 |
| `02-S03-ai-answer.png` | S03 | AI answer to the price questions (S$36.00) | 7.5 after the burst |
| `03-S04-host-top3.png` | S04 | Grouped questions on the host top 3 with suggested answers | |
| `04-S05-host-answer.png` | S05 | Host's spoken answer posted to viewers | 3.9 (2 s cancel window included) |
| `05-S06-fact-note.png` | S06 | Price correction note S$32 → S$36.00 | 1.8 |
| `06-S07-red-alert.png` | S07 | Full-screen HIGH compliance alert with "Say this instead" | 1.3 |
| `07-S07-escalated.png` | S07 | Not corrected within 5 s: escalated on the operator side | |
| `08-S07-corrected.png` | S07 | Corrected with the approved wording | 1.3 |
| `09-S09-operator-review.png` | S09 | Sensitive question (pregnancy) waiting for operator review | |
| `10-S10-required-done.png` | S10 | 3 / 3 required points | 1.9 |
| `11-S11-time-sale.png` | S11 | Time sale on: S$32.40 on the prompter, countdown chip | |
| `12-S12-switching.png` | S12 | Second switch cue: countdown banner | 1.9 |
| `13-S12-switched.png` | S12 | Deep Hydration Ampoule on air | 4.9 after the banner |
| `14-S13-fact-note.png` | S13 | Ingredient correction 10% → 4% niacinamide | 1.4 |
| `15-S14-summary-top.png` | S14 | Summary: AI recap and per-product numbers | recap 12.2 after End |
| `16-S14-summary-logs.png` | S14 | Summary: alert and fact log, agent latency | |

Agent latency in this run (p50 of the calls listed in the session state, no failures):

| Agent | p50 |
|---|---|
| compliance judge | 1.25 s |
| context judge | 1.52 s |
| fact checker | 1.33 s |
| comment triage | 1.38 s |
| answer composer | 3.53 s |
| broadcast summary | 12.6 s |
