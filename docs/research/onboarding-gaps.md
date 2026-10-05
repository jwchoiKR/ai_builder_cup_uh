# New-product onboarding: where the service is manual or hard-coded (10/5 night)

Why: the user found that a new product needs a fixed-template PDF and a hand-written `products.json`. Their words: "각 회사마다 제품 틀이 다 다를텐데 맞아야 한다고 하는것 자체가 엄청 문제", "수동인 프로세스들은 다 자동화가 되어야지", "제발 수동화가 아니라 LLM을 잘 활용하는 자동화된 플랫폼을 만들어보자".
Basic rule (user, 10/5): "문서 템플릿이 같아야 한다는 커스터머에게 기대는 행동은 하지말고, 우리가 다 달라도 맞출줄 알아야 한다. 그거는 기본이야." We never ask a customer to match a template, a section name, a marker or a file type. Every format difference is our job to absorb. We go back to the customer only when a fact is truly missing from all their documents, never because of how it is written.
Goal: a brand uploads whatever documents it has. LLMs build everything else, code does only arithmetic, deadlines, state and the gate before a public post, and people only approve.
Sources: the dev session's grep of the code (file:line), the Sonnet critic's review, and the codex/agy review (to be added).

## 1. Hand-written data (manual today)

- `data/products/products.json`: aliases, prompter points, approved and not-approved claims, qualified results, avoid-saying pairs and prices are written by hand. The fields are in `backend/app/models/data.py:44-49`. `eyebrow` and `hero_badge` have no default (`data.py:35-41`), so an extractor would have to invent marketing text.
- `data/products/*.md`: the sheets are hand-written. `passages.jsonl` is generated from them by a parser that expects fixed headings.
- `data/runsheets/demo_runsheet.json`, `data/promos/promos.json` (hand-computed `promo_prices`, one `set_cream_ampoule`) and `data/templates/notices.json` are hand-written.
- `backend/app/logic/catalog.py:34` sets `DEFAULT_RUNSHEET_ID = "daon_skincare_demo"`, the default session.
- Upload accepts only known codes. `setup.py:44` holds the regex "XX-XX-00", and `setup.py:512-515` returns 422 `unknown_product_code`. In the cloud the upload ends in "Manual in v1: upload to GCS, run the Vertex import" (`setup.py:522-528`).

## 2. Fixed sheet layout in code

- `backend/app/pipelines/setup.py:40-41`: the fixed section list (Product overview, Key facts, Key ingredients, How to use, In-house test results, Cautions, Approved on-air claims, FAQ).
- `setup.py:127, 147-203`: one parser per section: "item: detail" key facts, ingredient table, numbered steps, test table, approved/not-approved split.
- `setup.py:48`: the fixed `TEST_SUFFIX`.
- The same section names are hard-coded across the code:
  - `providers/retriever.py:15` PREFETCH_SECTIONS
  - `agents/answer_composer.py:17-31` intent→section maps
  - `agents/utterance_judge.py:85-86` SHEET_SECTIONS
  - `agents/fact_checker.py:19` CLAIMS_SECTION
  - `logic/verify.py:14, 104`
  - `pipelines/comments.py:322`: ingredient amounts from "Key ingredients" lines
  - `agents/brief.py:105-114`
  - `frontend/src/screens/operator/model.ts:75` and `host/hostSelectors.ts:64,84`: labels
- Template marks are treated as rules:
  - `*` means "say 'in our in-house test'" (`corrections.py:31`, `utterance_judge.py:47,74`).
  - "Label: value" tables are assumed (`verify._LABELLED`).
  - The `test_qualifier`/`in_house` patterns in `en.json` are fixed.
  - A brand that marks qualified claims with "†" or cites a third-party lab breaks the qualifier rule.
- Key-fact keys are code-addressed:
  - `audio_ws.py:34` keeps an allowlist (ph, pao_months, made_in...).
  - `setup.py:604` treats any value ending in % as an ingredient, so "SPF 50%" becomes an ingredient hint.

## 3. Our two products and the brand

- Alias and name lists are written for our two products: `catalog.py:37` `_GENERIC_ALIAS_BLOCKERS={"cream":"ampoule"}` and `fact_checker.py:22` `_NOT_NAMES`. Two products named "cream" cannot be told apart.
- "DAON LAB" is hard-coded:
  - `agents/brief.py:92-95`
  - `frontend/src/screens/host/Chat.tsx:35`
  - `Setup.tsx:15`
  - `viewer/ViewerView.tsx:58, 234-235`
  - `summary/SummaryView.tsx:19`
- Few-shot examples name our products and ids: answer_composer (9), fact_checker (8), utterance_judge (6), context_judge (5), draft_verifier (4), comment_triage (4, e.g. "niacinamide fits only the ampoule", "both products"), compliance_judge:89, brief_agent:58.
- BRAND-* rules are copied from the two sheets (`sg.json` source PRODUCT_SHEET "section 7"; BRAND-WHITENING source "Product sheet (Deep Hydration Ampoule)"). Rule descriptions carry carve-outs tuned to our approved wording ("tingling", "skin type", "5% panthenol").
- Every eval and sealed set uses these two product ids. A's 100% on the tune set follows from the tuning.

## 4. Market SG and currency SGD

- The defaults are SG:
  - `config.py:81` MARKET="SG"
  - `session.py:68`
  - `catalog.py:167`
  - `split_judges.py:100` and `rule_search.py:48` fall back to "SG"
  - `main.py:98` assumes the source `ASEAN_APPENDIX_III`
- The sheets are written in S$, and other markets rewrite the amounts by regex (`catalog.py:60-129`).
- Price conversion works by value, not by item (`catalog.py:70-72` `old.setdefault(was, now)`). Two items with the same SGD amount but different MY prices raise DataPackError. A third product at S$36 breaks the MY pack.
- Prices live in four places (products.json numbers, key_facts text, prompter point text, passages.jsonl).
- Unit words are a hand list: `verify.py:43` `_UNITS` (sgd, dollar, rm, myr, ringgit).

## 5. Category cosmetics

- `data/policy/intents.json`: the intents (skin_type_suitability, makeup_compatibility, routine_order...) and the condition slots are skincare. "multi" means both products.
- `models/agent_io.py:149-159`: five skincare slot keys are fixed in the schema.
- `logic/grouping.py:27` uses skincare intents.
- `comment_triage.py:183-220`: the fallback keywords (eczema, oily, pregnant) are skincare words.
- `docstore.py:18` falls back to "cosmetics". The market files have one category each. A new rule category needs hand wording in `en.json`, and `catalog.py:45-47` raises without it.
- The prompts say "skincare": `ai_pd.md:13` and `answer_composer.md:12,16`.

## 6. English only

- The defaults are English: `config.py:82`, `catalog.py:151,167`, `session.py:69`, and `stt.py:331` "en-US".
- `data/lang` has only `en.json`: reflex phrases, negation and reaction cues, number words, stopwords, stems.
- `shoutout.py:8-9`, `utterance_judge.py:304` `_CORRECTION`, `fact_checker.py:27` `_UNIT_WORDS` and `verify.py:43` are English regexes and lists.
- Word counts use `.split()`, which assumes spaces between words, so Chinese and Japanese break it: `comments.py:146`, `utterances.py:598`, `utterance_judge.py:135`.
- Arm A's word-overlap logic (corrections, publish relink, verify subject window) assumes English tokens.

## 7. Critique of the automation plan (Sonnet)

- **Approval must be per item:** AI may draft claims, cautions, qualified results, prices and percentages, but a person approves each one against a crop of its source. These items drive public posts and the "say instead" text.
- **Avoid correlated checks:** generated rule packs and test lines must not come from the same model family as the extractor, or the pass gate becomes circular. Test lines come from another model, labelled blind from the source sheet, plus a fixed generic corpus.
- **Measure recall as well as wrong numbers:** a missed not-approved claim or caution is silent leniency. Target 100% recall on cautions and not-approved claims. If a sheet is unreadable or the confidence is low, refuse and ask; never guess.
- **Arithmetic stays in code, keyed by item:** use currency minor units and state the rounding rule. Never reuse the by-value converter.
- **Order of work:** (a) onboard a third product first, which finds the hard-coded spots cheaply; (b) fix the schema, prices and aliases; (c) compare extraction methods; (d) rule layers; (e) generated tests and the pass gate.

## 8. Test: does arm A's lead survive a new product? (Sonnet, pre-registered)

- **Products:**
  - Product C: a third-party sheet in another layout, with a "†" qualifier, a third-party lab and prose claims.
  - Product D: a second cream priced S$36 and S$48, with a "panthenol 5%" line.
  - Both are onboarded only through the automated path. The dev side may not touch code between onboarding and results. Every break is logged as an onboarding failure.
- **Test sets:** sealed sets for C and D come from a different model, labelled blind from the sheet:
  - 9 types, at least 300 lines with 150 or more safe
  - verbal 40
  - 12 comment scenes with "cream" collisions
  - Arms A, F2 and B run on the same pack, 3 runs each.
- **Sample size:** 90 lines with 45 safe cannot separate 1.5% from 3.0% false alerts (2 vs 4 events). Use a paired bootstrap CI.
- **A's lead survives when all of these hold:**
  - A detection ≥ F2 on C+D
  - A false alerts ≤ F2 + 1.5 pt
  - 0 wrong public posts
  - A's drop from the old two products ≤ 2 pt
- **Also log** which A patches fired on C. If few fired, A was in effect prompt-driven there.
