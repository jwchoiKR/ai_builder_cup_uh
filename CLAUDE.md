# Live Studio (AI Builder Cup 2026)

Read `docs/HANDOFF.md` first: roles of each session, the user's rules, current state, how to run the evals and where the sealed sets are.

## Rules every session follows

- Answer the user in Korean.
- The dev session writes all app code. The planning/eval session writes only docs, data and evals.
- Never show or commit the sealed test sets (`D:\code_test\study\ai_builder_cup_git\sealed_sets\`). The dev session never reads that folder.
- Design choices are made by measurement: build every candidate as a switchable arm (`DESIGN_ARM`) and pick by the same evals. Fixed pass lines are in `docs/eval/proof-plan.md`.
- Viewer questions: post when the product info answers them, send to the operator when it does not.
- Deploy only to project `separk-cloocus`, and only after the user approves (the user runs `! bash deploy/cloudrun.sh`).
- Never commit `.env` or keys. Run a key-pattern scan of the diff from origin before every push, and push only when it finds nothing. Never force-push.
- Never edit agent permission or config files. Do not touch the user's Chrome.
- Call peers with explicit models: `codex exec -m gpt-6-astra -c model_reasoning_effort=high`, `agy --model gemini-3.8-flash-high`.
- At every plan, test, result and logic review, write the judge's view: what an AI Builder Cup judge would criticize and what change raises the score.
- The goal is a general platform: 100% on any unseen product. No product-specific prompts, few-shots, heuristics or rule carve-outs; products enter only via onboarding; pass/fail on a sealed pool of other products.
- Manual steps are design flaws: never ask a customer to match a template; absorb any document format; humans only approve.
- If our logic misses its pass lines after a small patch budget (1-2 rounds), scrap it and rebuild; set kill criteria before testing.
- Decks and explainer HTML go in `docs/decks/` (build scripts in `docs/decks/build/`).

## Quirks

- STT chirp_3 works only in region `us` (403 in Asia). Gemini 3.5 Flash-Lite and 3.8 Flash work only on the global endpoint.
- Cloud Run runs `STORE=memory` with max-instances 1. Firestore `live-studio` is empty, so read past shows from Cloud Logging.
- Gemini 3 context caching needs a prefix of 4,096 tokens or more. Only the fact checker benefits today.
- Korean output from Python on this Windows machine needs `PYTHONIOENCODING=utf-8`.
- Writing eval or corpus task text through bash `python -c "..."` or an unquoted heredoc expands `$80` to empty ("S$80" became "S0" in sealed pool 3). Use the Write tool or `<<'EOF'`.
- PowerShell flattens `@(@("a","b"))` into one list, so a one-element list of arrays loops over strings. Write `@(,@("a","b"))`.
- Eval scorers must treat zero-decimal currencies (KRW, JPY, VND, IDR) as whole units; the app already does (D-243).
- Vertex AI Search defaults drop low-relevance hits ("It cures eczema" returned nothing). Use `relevanceThreshold: LOWEST`, `pageSize` 5-10 and the market filter.
- Code may overrule a model verdict, but never silently: look for "fact claim dropped by code" and "compliance violation dropped by code" in the logs. `eval_adversarial` rows carry `dropped: [{reason, ...}]`. A right model answer with no alert is almost always one of these drops (D-248, D-250, D-260).
- `FACT_MODE=docs` (FD, default) reads a release's original files from `<ONBOARDING_DIR>/<job_id>/files.json`. A release without stored files behaves as `record`. Record fields added after a release was made (pack counts, offer conditions, target group) appear only after re-onboarding.

## Handoff by role (10/6 06:00, branch `multi_agent_test` at 427efdb, pushed)

Cloud: `live-studio-us` revision 00009-qcf runs 41411fd (deployed 10/6 morning, IAP on). Where things stand: unseen-product live detection is about **84%** (fresh sealed pool 3, one clean run, fbb8aa7: 84.6%; pool 2: 83-84%). The goal is 100%. Onboarding passes product/governance/safety/offers on nearly all 21 sealed products with at most 10 human checks each. Numbers and history: `docs/eval/proof-plan.md` (last sections), `docs/HANDOFF.md`. Nothing is running.

### Planning/eval session (writes docs, data, evals; never app code)
- Owns: sealed pools, scoring, the measurement loop, decks, handoff, coordinating dev/critic/peers, commit+push of the branch.
- Not in git (copy `D:\code_test\study\ai_builder_cup_git\handoff_bundle_1006.zip` to another PC by a private channel, never via the repo): `sealed_sets/` (pools, results, scorers, LABEL_CHANGES, `run_scripts/` with every .ps1 used), `ops_scripts/`, the `google-slide-deck` and `natural-writing` skills (unzip into `~/.claude/skills/`; deck build scripts hard-code that skill path, so adjust the path on the new PC), and the Claude memory files. Also set up `.env`, `gcloud auth application-default login`, and the codex and agy logins. Peer sessions (dev, critic) are local to this PC; start new ones from this file.
- Sealed pools (outside the repo, `D:\code_test\study\ai_builder_cup_git\sealed_sets\`): `onboarding/` pool 1 (P1-P9 docs, live_P1-6), `onboarding2/` pool 2 (Q1-Q6), `onboarding3/` pool 3 (R1-R6; known quirk "S0" offers, see its README). Pools 1-3 are all "seen" now: **build pool 4 before any new claim** (copy the onboarding3 recipe: codex `task_corpus.md` written with the Write tool, `render3.py`, codex `task_live_lines.md`, Sonnet `task_blind_truth.md` + `task_blind_live.md`, then `finalize.py`).
- One measurement round: worktree at the candidate commit (`armtree`, `armtree3`, `armtree4`; `deploy158` is dev's), `uv sync`, then `scripts/eval_onboarding.py <by_product\Xn> --out ... --verify-mode lean` per product, `sealed_sets/approve_sealed.py` (approval as the API does; `--prefix`, set `MARKET=MY` for MY-only products), `sealed_sets/store_files.py` (FD files), `scripts/eval_adversarial.py --runs 3 --release <id> --cases live_Xn.jsonl --out ...`. Examples: `armtree/run_pool3.ps1`, `armtree3/run_p3b.ps1`. Run live evals serially; parallel runs cause timeouts.
- Scoring: always `sealed_sets/rescore_live.py <raw.json> <cases> --main mainvalue.json --patch label_patch_live.json --rule-map lawsrc/rule_map_supp.json` (blind main values, field/kind aliases, pre-registered rule maps, no-penalty extras). Onboarding: `onboarding/score_groups.py <dir> <truth>`; safety by meaning needs the critic (keyword matching fails across languages). Every label/scorer change goes to `sealed_sets/LABEL_CHANGES.md` and is reported apart from logic gains.
- To dev: send failure CLASSES with made-up examples, never sealed text. Read `row["dropped"]` first: most misses were code drops of right verdicts.
- Next: pool 4; the open items in the dev list below; deck refresh after new numbers (`docs/decks/build/*.py`, then google-slide-deck `check.py`, natural-writing `check_text.py`, `shots.py`, codex image review).

### Dev session (writes all app code)
- Latest: 809adbf (D-262). Defaults: `FACT_MODE=docs`, Flash-Lite `FACTS_THINKING=LOW`, `FACT_TIMEOUT_MS=FACT_LATE_MS=5000`, compliance 3 s, `VERIFY_MODE=lean` in evals. Decisions D-243…D-262 in `docs/DECISIONS.md`.
- Conventions: product-neutral fixes only (no product words, prompts use fictional examples); pipeline tests through `eval_adversarial.run_case` with made-up releases; every code drop logged with a reason; record shape changes need re-onboarding to measure.
- Open (classes): HIGH compliance alerts on fact-error lines for food/children products (wrong HIGH 4-7 per pool); children's toothpaste stuck at 72% (usage/age lines); false alerts 7.4% on two products (restatements in other scripts); Chinese-document product swings 67-78% across runs; onboarding quality (Malay/Chinese-only cautions, padded caution lists, archived-size "not orderable" fact missing); multiplicatives/number words only for `en` so far.

### Critic (Sonnet session `ai-builder-cup-uh-38`)
- Does: blind truth from documents only, blind live labels, grading onboarding safety by meaning, verdicts on label policy and scorer fairness. Never shown to dev.
- Brief it with the exact files it may read and the output file; ask for per-item verdicts with reasons; apply only what it approves (its rulings so far are in LABEL_CHANGES.md: main values, negated cautions as fact catches with no-penalty compliance extras, rule-map tightening).

### Peer models
- codex (`codex exec -m gpt-6-astra -c model_reasoning_effort=high --skip-git-repo-check -o out.md - < task.md`): corpora, live lines, blind main values, deck image review (`--image`), cross-check of research. agy (`agy --model gemini-3.8-flash-high`) for a second opinion. Run codex in the background with a done-marker file; write task files with the Write tool.

### Team (humans, user's plan 10/5)
- Dev lead (user): decisions, merges, deploy approval, IAP removal, Gemini Live timing.
- Host tester: one real host session with the assistant off/on (correction success, intervention time, alerts per hour), real voice latency.
- Workflow/performance verifier: owns pool 4+ and reruns; reads `docs/decks/workflow_detail.html` and proof-plan first.

### User-only (never without approval)
- Deploy (`! bash deploy/cloudrun.sh`), IAM/IAP changes, login removal, new cloud resources, Gemini Live arm timing.
