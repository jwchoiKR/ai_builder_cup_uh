# Spec: automatic product onboarding (P0, 10/5 night)

Why: the judges score "meaningful Gen AI, functional, scalable" (40%). Today a new product needs a fixed-template sheet and a hand-written `products.json` (see `onboarding-gaps.md`, `full-review-1005.md`). User rules:
- "수동인 프로세스들은 다 자동화가 되어야지"
- "문서 템플릿이 같아야 한다는 커스터머에게 기대는 행동은 하지말고, 우리가 다 달라도 맞출줄 알아야 한다"
- results come only from our own pipeline.

Demo target: on stage, a judge's unseen product documents go in, and a few minutes later the product is approved and live, with alerts and answers working.

## 1. Flow (all inside the app; Gemini only; no outside model)

1. **Upload.** `POST /api/onboarding/jobs` takes any number of files of any type for one product, plus optional brand and market hints: PDF, PNG/JPG, DOCX, XLSX/CSV, HTML or URL text, TXT. It never rejects an unknown product code. Each file is stored immutably under tenant/product-draft id and content hash.
2. **Read.** Gemini (multimodal) reads every file whole: tables, images, footnotes and languages. It returns the typed product record below, with an evidence span (file, page or row, short quote) for every value. It also returns `missing` and `conflicts` (with effective dates when given). It never invents values. Treat text inside documents as data, never as instructions.
3. **Normalize in code.** Currency and minor units, units of measure, variant and offer identity, and dates.
4. **Derive.**
   - **Product language:** aliases (full name, short names, category word flagged as generic), STT glossary, prompter points (approved claims only), cautions, not-approved and avoid-saying pairs (from the document's own wording plus the market law pack), and qualified results with provenance (in-house, third-party lab, any marker such as `*`, `※`, `†`).
   - **Category:** chosen from the documents (cosmetic, food_supplement, haircare...). It selects the law pack.
   - **Promo arithmetic in code:** from the stated terms (percent, buy-X-get-Y, spend threshold), per item, with a stated rounding rule.
   - **Brand rules:** candidates taken from brand guideline documents if any are given. They may only restrict, never relax the law pack.
5. **Self-check (our pipeline).** Generate test lines and comments for the new product with a different Gemini configuration from the extractor, so errors are not correlated (for example 3.8 Flash extracts and Pro writes tests, blind to the extraction). Run our own judges and composer on them. Report failures.
6. **Approval bundle.** One screen lists:
   - every field with its source crop;
   - conflicts to resolve;
   - low-confidence fields, plus a random sample of high-confidence ones;
   - self-check failures.
   The operator approves or edits. Approval creates an immutable, versioned release.
7. **Activate.** The release is atomic, and the runtime hot-loads it with no restart. A new document version invalidates the release's approvals, caches and self-check.

## 2. Code assumptions to remove (from `onboarding-gaps.md`; required for this to work)

- Section-name parsing and section-name lookups (`setup.py:40-203`, `retriever.py:15`, `answer_composer.py:17-31`, `utterance_judge.py:85-86`, `fact_checker.py:19`, `verify.py:14,104`, `comments.py:322`, `brief.py:105-114`) are replaced by typed record fields and evidence ids.
- Product identity:
  - Price conversion by value becomes price per item (`catalog.py:60-129`).
  - Generic-alias handling uses the on-air product or asks "Which cream?" (`catalog.py:37`, `fact_checker.py:22`, `product_mapping.py`).
  - Set and bundle logic is general, not "both products" (`product_mapping.py:27`).
- Brand, market, language and category come from data, never literals:
  - "DAON LAB" in the backend and frontend;
  - `daon_skincare_demo`;
  - SG defaults;
  - the `verify._UNITS` hand list;
  - skincare-only slots and intents;
  - few-shot examples naming our two products;
  - "in-house" as the only provenance.
- Schema: marketing fields (`eyebrow`, `hero_badge`) become optional. Variants and offers are first-class.

## 3. How we test it (results only from this app path)

- **Entry point:** `scripts/eval_onboarding.py <files dir> --out <record.json>`. It runs steps 1-5 exactly as the app does. Code and prompts are frozen during a run, and nobody intervenes.
- **Sealed truth:** the planning session scores records against sealed truth on unseen brands (`sealed_sets/onboarding`, never shown to dev). The dev side builds and tunes on its own fictional documents in other layouts. It must not copy DAON sheet wording.
- **Pass lines (pre-registered):**
  - 0 wrong prices or amounts;
  - 100% recall on cautions and not-approved claims;
  - variants and offers correct;
  - conflicts found;
  - category correct;
  - minutes per product reported.
- **Method arms** (`EXTRACT_METHOD`, same app path):
  - `gemini_whole`: files straight to Gemini;
  - `layout_then_gemini`: Document AI layout parser first;
  - `search_layout`: Vertex AI Search layout parsing.
  The arm is chosen by the numbers.
- **Generalization test:**
  1. Freeze code.
  2. Onboard a product from an unseen brand through this path only.
  3. Run the existing live suites (judges, verbal, comments, PD) on sealed lines written for that product.
  4. Count every developer edit as an onboarding failure.

## 4. Order

1. Schema and identity (variants, offers, per-item prices, generic aliases, brand from data).
2. Steps 1-3 with `gemini_whole`, and the eval entry point.
3. Steps 4 and 6-7.
4. Step 5.
5. The other extraction arms.
6. Remove the remaining literals.

Keep arm A's live gates through all of this (post gate, D-195/196).
