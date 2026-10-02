# Orchestrator branching on tricky sentences · 2026-10-02

**What runs:**
- Each case is text injected as a final transcript (what STT would send) into a fresh live session.
- The agents are real: `gemini-3.5-flash-lite` on Vertex AI for the UtteranceJudge and the FactChecker; the Comment Triage and Answer Composer also run for the case with a comment burst.
- The checks look only at what the orchestrator did with the agents' answers: compliance alerts, fact notes, prompter points, the host-answer post and the product switch.
- **Runs:** 3 per case, because model answers can vary. Script: `backend/scripts/eval_orchestrator.py`.
- **Unit tests:** the same branches with scripted agents are in `backend/tests/test_orchestrator_cases.py`.

**Result:** 42/42 case runs passed.

| # | Input (STT text) | Why it is tricky | Expected | Pass | What happened (a failing run if any, else the last) | What the agents said |
|---|---|---|---|---|---|---|
| 1 | “This cream cures eczema.” | plain disease claim | alert ASEAN-2D-DISEASE; no fact note | 3/3 | alert ASEAN-2D-DISEASE; no fact note | judge: product_talk, ASEAN-2D-DISEASE (claim) (1388 ms)<br>facts: no claim (1337 ms) |
| 2 | “Your breakouts will be gone in a week.” | acne claim with no listed keyword | alert ASEAN-3-SKIN-ACNE; no fact note | 3/3 | alert ASEAN-3-SKIN-ACNE; no fact note | judge: product_talk, ASEAN-3-SKIN-ACNE (claim) (1856 ms)<br>facts: no claim (1243 ms) |
| 3 | “It doesn't cure eczema, it's just a moisturiser.” | risky words, but negated | no alert; no fact note | 3/3 | no alert; no fact note | judge: product_talk, ASEAN-2D-DISEASE (negated) (1685 ms)<br>facts: no claim (1152 ms) |
| 4 | “Jun is asking if it heals acne scars.” | risky words inside a viewer's question | no alert; no fact note | 3/3 | no alert; no fact note | judge: question_readout, ASEAN-3-SKIN-SCARS (quoted) (1380 ms)<br>facts: no claim (1167 ms) |
| 5 | “My cat literally cured my bad mood today, haha.” | 'cured' but not about the product | no alert; no fact note | 3/3 | no alert; no fact note | judge: chit_chat, no violation (1254 ms)<br>facts: no claim (1019 ms) |
| 6 | “Honestly, it's the best moisturiser in Singapore.” | MEDIUM rule, not HIGH | MEDIUM alert; no fact note | 3/3 | alert BRAND-SUPERLATIVE; no fact note | judge: product_talk, BRAND-SUPERLATIVE (claim) (1609 ms)<br>facts: no claim (1194 ms) |
| 7 | “In our in-house test, twenty-nine of thirty-two people said their skin felt less dry after two weeks.” | numbers and a benefit, all approved | no alert; no fact note | 3/3 | no alert; no fact note | judge: product_talk, no violation (1683 ms)<br>facts: test_result supported (29 of 32) (1475 ms) |
| 8 | “The cream has five percent ceramide NP.” | 5% belongs to panthenol; ceramide NP is 1% | no alert; fact note ingredient_amount | 3/3 | no alert; fact note ingredient_amount | judge: product_talk, no violation, points cr-p2 (1417 ms)<br>facts: ingredient_amount contradicted (5% ceramide NP → 1%) (1415 ms) |
| 9 | “The live price today is thirty-six dollars.” | a price that is right | no alert; no fact note | 3/3 | no alert; no fact note | judge: product_talk, no violation, points cr-p6 (1479 ms)<br>facts: price supported (S$36) (1537 ms) |
| 10 | “It repairs damaged skin, and it's only thirty dollars today.” | two branches at once | HIGH alert; fact note price | 3/3 | alert ASEAN-DP5-PHYSIOLOGICAL; fact note price | judge: product_talk, ASEAN-DP5-PHYSIOLOGICAL (claim) (1550 ms)<br>facts: other contradicted (repairs damaged skin → Not approved), price contradicted (S$30 → S$36.00) (1610 ms) |
| 11 | “It's a lightweight gel-cream, so it absorbs really quickly.” | plain product talk | no alert; no fact note; prompter cr-p1 | 3/3 | no alert; no fact note; prompter cr-p1 | judge: product_talk, no violation, points cr-p1 (1603 ms)<br>facts: texture supported (lightweight gel-cream), texture supported (absorbs quickly) (1720 ms) |
| 12 | “Raj is asking if it's OK for oily skin. Yes, it's lightweight, so just use a smaller amount on oily areas.” (after burst B2) | a question read out, then answered | no alert; no fact note; host answer posted | 3/3 | no alert; no fact note; host answer posted | judge: answer, no violation, points cr-p1, answer (1535 ms)<br>facts: usage supported (use a smaller amount on oily areas) (1270 ms) |
| 13 | “We'll get to the Deep Hydration Ampoule a bit later.” | names the next product, no transition | no alert; no fact note; no switch | 3/3 | no alert; no fact note; on air: cream | judge: other, no violation (1648 ms)<br>facts: no claim (1358 ms) |
| 14 | “Okay, now let me show you our Deep Hydration Ampoule.” / “It has four percent niacinamide and helps skin look more radiant.” | named transition, then a fact about it | no alert; no fact note; switch to the ampoule | 3/3 | no alert; no fact note; on air: ampoule | judge: transition, no violation, transition (1435 ms)<br>facts: no claim (992 ms)<br>judge: product_talk, no violation, points am-p1,am-p4 (1558 ms)<br>facts: ingredient_amount supported (4% niacinamide) (1180 ms) |
