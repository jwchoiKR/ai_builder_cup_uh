# Multi-release show: the minimal version (user-approved 10/6, built as D-279)

A show presents 2 or 3 approved releases in order. The live pipeline already handled several products: the old demo
ran two. The work is to build one show pack from the release packs. The judges did not need rewriting.

## Built
- **API:** `POST /api/sessions {"release_ids": [r1, r2]}` takes 2-3 different releases in segment order. One id behaves
  as `release_id`. Each segment keeps its release's planned time, so the time is split equally. The API answers 404
  for an unknown release and 400 for more than 3 releases, a repeated one, or a release that is not buildable for the
  show's market (no price there, another currency).
- **Hub:** the "Previously approved products" picker keeps its first-product select. "Then" checkboxes add up to 2
  more products, numbered in the order they were ticked. There is no drag and no minutes field.
- **Show pack** (`onboarding/show.py`): each release's pack is built as for a one-product show, and the packs are merged:
  products, passages, promos, the run sheet (one segment per release, with its required points), and the rules. A
  rule remembers the products it came with (`DataPack.rule_products`), and `DataPack.releases` maps each product to
  its release.
- **Attribution:**
  - A line that names no product goes to the product on air, in run-sheet order, as in the demo.
  - A line that clearly names one product (its full name or a short name only it has) goes to that product.
  - An ambiguous shared alias names none, so the line goes to the product on air. There is no candidate check yet. It
    is added only if the sealed multi-product pool shows false alerts.
- **Rules:** the compliance judge gets the rules of the product on air, a pending switch's target, and any product
  the line or the last 2 lines name, chosen in code. A verdict on a rule the line was not given is dropped. A reflex
  chip from another product's law is not shown. An alert keeps the product on air when the line was spoken.
- **Facts:** the fact checker uses the on-air product's release files as its context cache. At the start of a show,
  every release's cache is warmed, with no rotation on a switch. A quote is checked against every release's files.
- **STT and prompter:** the phrase hints are every release's brief glossary, with the product on air at connect first.
  The prompter shows each segment's own points.

## Out of scope
- Cross-product offers: a set or bundle price, and time-sale stacking. Offers stay per release.
- More than 3 releases.
- Cold-start recovery of a running show (waits for the Firestore work).
- The candidate check on shared aliases.
- The demo moves to one 2-release show next.

## Tests (made-up releases) and pass lines
- **Tests** (`tests/test_multi_release.py`), with a skincare cream (the market's cosmetics law) and a kitchen kettle
  (no law pack):
  - the order of the products, and each product's own law;
  - no alert from the cream's law on a kettle line that names nothing, and the cream's law when the line names the
    cream;
  - a wrong-product price caught with the right release's quote;
  - the API with 2 releases, 4 releases, and an unknown release.
- **Pass lines** (planning session, measured on a sealed multi-product pool):
  - wrong-product value caught 95% or more, with 0 false alerts on correct values;
  - 0 false alerts on a matching value said with a shared alias;
  - 0 alerts from another category's rules;
  - mixed-show detection at most 2 points below single-release;
  - wrong HIGH 0;
  - alert p95 3 s or less.
- **Kill:** any wrong HIGH, or more than 2 points below baseline after 2 patches. Then fall back to the union of all
  rules.
