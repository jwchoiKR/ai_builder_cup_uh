# Multi-release show: design draft (dev, 10/6; for review before any code)

A show presents N approved releases in order. The live pipeline already handles several products: the old demo ran two
products with a set price, a time sale, switches and cross-product checks. The work is mostly building one show pack from
N release packs, not rewriting the judges.

## 1. Show pack and API
- `POST /api/sessions {"release_ids": [r1, r2], "durations_s": [600, 600]}`. The current `release_id` stays as a list of
  one. The session stores the ids, and a show is pinned to those release versions.
- `show_pack(base, [packs])` merges the N single-release packs: products, passages, prompter points, promos and
  glossary. The run sheet is one segment per release, in the given order. A segment's required points are that
  release's brief points. The pack cache key is the tuple of release ids.
- Rules differ by category (a kettle and a supplement get different law packs). Each rule keeps the products it
  applies to. The compliance judge gets the rules of the product on air, plus the rules of the target during a
  pending switch. Today it gets every rule of the one product.
- Hub: the "approved products" picker becomes a multi-select with drag order and a minutes field, then "Start a show".
- Market and currency must match across releases. If they do not, the API refuses with 400.

## 2. Cross-product offers
A set price or bundle across releases belongs to neither product's documents. **Pick: an onboarded show offer pack.**
The seller uploads an offer document (any format). The reader extracts offers that name products. Code matches each
named product to a release in the show by name or alias. A person approves the matches and the terms. The pack is
write-once, like law and brand packs.
- Why not read it from one release that names the other: the offer would change when that release is re-onboarded, a
  release would carry another product's price, and approval would be per product, not per show.
- A time sale on one product is that release's own offer (D-223). If the seller puts it in the offer document, it
  comes from the show offer pack.
- Set totals are computed in code from the matched releases' prices (D-244 L2). The fact checker and the composer get
  them as offer passages.

## 3. Attribution in live judging
- Switching stays as it is: the context judge's `switch`, the operator switch, and "a product the last lines named
  stays citable" (D-172). Aliases come from every release. Two releases with the same alias ("the serum") make that
  alias ambiguous: `product_by_alias` returns no product, and the judges fall back to the product on air.
- Wrong-product facts: the fact checker gets passages of the product on air plus the named or pending product. "The
  serum is S$30" when S$30 is the cream's price is a contradiction with the serum's price. This is the demo's
  existing case, and it needs a test on releases.
- FD files (`FACT_MODE=docs`): one context cache per release, created when its segment starts and at a pending switch,
  and dropped after the switch. At most 2 caches live at a time. Each cache needs at least 4,096 tokens and is billed
  per hour, so a 5-release show costs about 2 caches, not 5. If a cache fails, the check runs without it (today's
  behaviour).

## 4. Brief, STT, prompter, comments
- STT phrase hints: the union of the releases' brief glossaries, with the product on air first. This stays within
  chirp_3's phrase limit; the lowest-ranked terms are cut first.
- Prompter: each segment shows its release's brief points, caution slots (D-276) and offer points (D-272). Show offer
  points appear in every segment whose product they name.
- Comments: the triage gets every product's name and aliases. A comment that names a product is attributed to it. An
  unnamed one goes to the product on air (the current rule).

## 5. Stays single-release
Onboarding, approval, the brief, law and brand pack selection, translation and the test drive. A show never edits a
release.

## 6. Demo migration
The 2 demo PDFs become 2 releases, plus the demo brand policy as a brand pack and the set price and time sale as a
show offer pack. The demo API starts the 2-release show. The comment and host scripts move to the release product ids.

## 7. Tests (made-up releases only) and risks
- Tests:
  - A 2-release show in two categories: each segment gets only its own law rules.
  - A switch, and a line about the other product: the fact checker cites the right release.
  - A wrong-product price.
  - A set price from a show offer pack, with the total computed in code.
  - Shared alias ambiguity.
  - Comments naming each product.
  - A cold start: the show restarts from the stored ids.
  - Mismatched markets are refused.
- Risks:
  - Rule filtering by product could drop a rule that should apply during a fast switch. Mitigation: the pending
    target's rules are added.
  - Context cache cost with many releases.
  - Matching show offers to products by name. Mitigation: a person approves the matches.
  - A longer STT phrase list.
  - The demo depends on the new offer pack type before it can run as one show.
