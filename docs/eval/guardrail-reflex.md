# Code guardrail alone (Reflex, before the LLM) · 2026-10-02

**What runs:** for every utterance eval case, what the orchestrator does before the judge, and what it falls back to when the judge fails (§8.4.3). The Reflex keyword scan (claim_rules.json phrases, negation and quote cues) creates provisional alerts; `apply_judge_failure` shows a HIGH hit that is neither negated nor quoted, and clears the rest. No model is called. Script: `backend/scripts/eval_guardrails.py`.

**Ground truth:** `data/eval/utterance_cases.jsonl`. Cases with `expected.compliance` are labelled; the others make no claim (prices, answers, transitions) and count as safe.

## Result
- **Labelled cases (19):** 18/19 handled correctly by code alone (95%).
- **HIGH violations:** 9/10 caught with the right rule; 1 missed.
- **MEDIUM violations:** 3. The fallback never shows MEDIUM alerts, so only the judge can.
- **Safe sentences (labelled and unlabelled, 26):** 26 passed, 0 false alarms.
- **Unlabelled cases (20):** 20/20 correct (no alert).

| Case | Sentence | Truth | Keyword hit | Code-only result | Correct |
|---|---|---|---|---|---|
| U01 | Use it every night and your wrinkles will disappear overnight. | HIGH violation · ASEAN-3-SKIN-AGEING | 'wrinkles will disappear' → ASEAN-3-SKIN-AGEING | alert ASEAN-3-SKIN-AGEING | ✓ |
| U02 | This cream literally cures eczema. | HIGH violation · ASEAN-2D-DISEASE | 'cures' → ASEAN-2D-DISEASE, 'eczema' → ASEAN-2D-DISEASE | alert ASEAN-2D-DISEASE | ✓ |
| U03 | The ampoule treats acne, so you'll never break out again. | HIGH violation · ASEAN-3-SKIN-ACNE | 'treats acne' → ASEAN-3-SKIN-ACNE | alert ASEAN-3-SKIN-ACNE | ✓ |
| U04 | Once you use it, the results are permanent. | HIGH violation · ASEAN-2E-PERMANENT | 'permanent' → ASEAN-2E-PERMANENT | alert ASEAN-2E-PERMANENT | ✓ |
| U05 | It regenerates your skin cells from the inside. | HIGH violation · ASEAN-DP5-PHYSIOLOGICAL | 'regenerates' → ASEAN-DP5-PHYSIOLOGICAL | alert ASEAN-DP5-PHYSIOLOGICAL | ✓ |
| U06 | It even removes your old acne scars. | HIGH violation · ASEAN-3-SKIN-SCARS | 'scars' → ASEAN-3-SKIN-SCARS | alert ASEAN-3-SKIN-SCARS | ✓ |
| U07 | It's totally safe for pregnant women, don't worry. | HIGH violation · ASEAN-2D-VULNERABLE | 'safe for pregnant' → ASEAN-2D-VULNERABLE, 'totally safe' → BRAND-ABSOLUTE-SAFETY | alert ASEAN-2D-VULNERABLE | ✓ |
| U08 | Honestly this is the best moisturiser in Singapore. | MEDIUM violation · BRAND-SUPERLATIVE | 'the best' → BRAND-SUPERLATIVE | no alert | ✓ |
| U09 | It whitens your skin in two weeks. | MEDIUM violation · BRAND-WHITENING | 'whitens' → BRAND-WHITENING | no alert | ✓ |
| U10 | Think of it like a prescription cream, but cheaper. | MEDIUM violation · BRAND-MEDICINE-LIKE | 'prescription' → BRAND-MEDICINE-LIKE | no alert | ✓ |
| U11 | You'll look ten years younger after one bottle. | HIGH violation · ASEAN-3-SKIN-AGEING | 'years younger' → ASEAN-3-SKIN-AGEING | alert ASEAN-3-SKIN-AGEING | ✓ |
| U12 | It kills the bacteria on your skin. | HIGH violation · ASEAN-3-SKIN-ANTIMICROBIAL | no keyword | no alert | ✗ |
| U13 | Just to be clear, it does not treat acne. It's a moisturiser. | safe (negated) | 'treat acne' → ASEAN-3-SKIN-ACNE (negated) | no alert | ✓ |
| U14 | Someone asked if it cures eczema. No, it's a cosmetic, it doesn't treat any condition. | safe (quoted) | 'cures' → ASEAN-2D-DISEASE (quoted), 'eczema' → ASEAN-2D-DISEASE (quoted) | no alert | ✓ |
| U15 | It helps keep skin hydrated for up to 24 hours in our in-house test. | safe | no keyword | no alert | ✓ |
| U16 | It helps reduce the look of fine dryness lines. | safe | no keyword | no alert | ✓ |
| U17 | We can't say it removes wrinkles, but it helps skin look more radiant with continued use. | safe (negated) | 'removes wrinkles' → ASEAN-3-SKIN-AGEING (negated) | no alert | ✓ |
| U18 | I'm scared of heavy creams, but this one is light. | safe | no keyword | no alert | ✓ |
| U19 | And today the live price is only thirty-two dollars. | safe | no keyword | no alert | ✓ |
| U20 | The live price today is thirty-six dollars. | safe | no keyword | no alert | ✓ |
| U21 | This one has ten percent niacinamide. | safe | no keyword | no alert | ✓ |
| U22 | There's four percent niacinamide in here. | safe | no keyword | no alert | ✓ |
| U23 | It's a hundred ml tube, so it lasts forever. | HIGH violation · ASEAN-2E-PERMANENT | 'lasts forever' → ASEAN-2E-PERMANENT | alert ASEAN-2E-PERMANENT | ✓ |
| U24 | The set with the ampoule is sixty-two dollars. | safe | no keyword | no alert | ✓ |
| U25 | I just love how it feels on my skin. | safe | no keyword | no alert | ✓ |
| U26 | With the time sale it's thirty-two forty now. | safe | no keyword | no alert | ✓ |
| U27 | With the time sale it's thirty dollars now. | safe | no keyword | no alert | ✓ |
| U28 | Raj is asking if it's OK for oily skin. Yes, it's a lightweight gel-cream, just use a bit less on oily areas. | safe | no keyword | no alert | ✓ |
| U29 | Someone is asking about oily skin, I'll get to that in a second. | safe | no keyword | no alert | ✓ |
| U30 | For oily skin? Hmm, let me check with the team. | safe | no keyword | no alert | ✓ |
| U31 | Yes you can use it under makeup, put sunscreen on after the cream and then your makeup. | safe | no keyword | no alert | ✓ |
| U32 | It's a lightweight gel-cream so it absorbs really quickly. | safe | no keyword | no alert | ✓ |
| U33 | Inside you've got one percent ceramide NP, five percent panthenol and three percent squalane. | safe | no keyword | no alert | ✓ |
| U34 | Someone is asking about the ampoule, we'll get to it in a minute. | safe | no keyword | no alert | ✓ |
| U35 | Okay, now let me show you our Deep Hydration Ampoule. | safe | no keyword | no alert | ✓ |
| U36 | This ampoule goes on before the cream, it's a watery gel, two to three drops after toner. | safe | no keyword | no alert | ✓ |
| U37 | Going back to the cream for a second, it's fragrance free. | safe | no keyword | no alert | ✓ |
| U38 | Let me correct that. It helps keep your skin hydrated for up to twenty-four hours in our in-house test. | safe | no keyword | no alert | ✓ |
| U39 | Sorry, my mistake, the live price is thirty-six dollars. | safe | no keyword | no alert | ✓ |

## New phrasing: the 14 tricky sentences of `orchestrator-cases.md` (15 lines)
The keyword list in `claim_rules.json` was written with the eval set above in mind. These sentences were not, so they show how the guardrail does on unseen wording.

- **Result:** 13/15 correct.

| Sentence | Truth | Keyword hit | Code-only result | Correct |
|---|---|---|---|---|
| This cream cures eczema. | HIGH violation | 'cures', 'eczema' | alert | ✓ |
| Your breakouts will be gone in a week. | HIGH violation | – | no alert | ✗ missed (no listed phrase) |
| It doesn't cure eczema, it's just a moisturiser. | safe (negated) | 'cure', 'eczema' (negated) | no alert | ✓ |
| Jun is asking if it heals acne scars. | safe (quoted) | 'heals', 'scars', 'heals acne' (quoted) | no alert | ✓ |
| My cat literally cured my bad mood today, haha. | safe (off topic) | 'cured' | alert | ✗ false alarm (no context) |
| Honestly, it's the best moisturiser in Singapore. | MEDIUM violation | 'the best' | no alert (MEDIUM needs the judge) | ✓ |
| In our in-house test, twenty-nine of thirty-two people said their skin felt less dry after two weeks. | safe | – | no alert | ✓ |
| The cream has five percent ceramide NP. | safe (a fact error, not compliance) | – | no alert | ✓ |
| The live price today is thirty-six dollars. | safe | – | no alert | ✓ |
| It repairs damaged skin, and it's only thirty dollars today. | HIGH violation | 'repairs damaged skin' | alert | ✓ |
| It's a lightweight gel-cream, so it absorbs really quickly. | safe | – | no alert | ✓ |
| Raj is asking if it's OK for oily skin. Yes, it's lightweight, so just use a smaller amount on oily areas. | safe | – | no alert | ✓ |
| We'll get to the Deep Hydration Ampoule a bit later. | safe | – | no alert | ✓ |
| Okay, now let me show you our Deep Hydration Ampoule. | safe | – | no alert | ✓ |
| It has four percent niacinamide and helps skin look more radiant. | safe | – | no alert | ✓ |

With the LLM judge, all 14 cases were right in 3 of 3 runs (`orchestrator-cases.md`).
