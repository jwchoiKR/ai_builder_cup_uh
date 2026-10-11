# Open issues

Issues found and waiting for a team decision. Each entry: what happens, where in the code, how it was found, and the status.

## I-1. Every screen opened without `?session=` joins the same show (10/10)

**What happens.** A screen opened without `?session=<id>` in its address asks `GET /api/demo/current`. That returns the newest show that has not ended and uses the demo releases, or makes a new one when there is none (D-332). So everyone who opens the app without a session id sees the same show: one person's lines, alerts, switches and dismissals appear on every other person's host, operator and viewer screens. Sessions themselves are separate; only the default landing is shared.

**Where.**
- `frontend/src/app/router.tsx:1, 98`: no `?session` means `/api/demo/current`.
- `backend/app/api/demo.py:83-90` `demo_current`: newest non-ended demo show, else a new one.

**How it was found.** On 10/10 the planning session ran a basic check on revision 00011 (a session with the two DAON demo releases, lines injected through `POST /sessions/{id}/transcripts`). The user saw the test show on their own browser without opening its session link.

**Why it matters.** Several judges or testers opening the public URL at the same time would interfere with each other's demo.

**Status.** The user will discuss the fix with the team. No code change yet.

## I-2. A health question the product info answers reaches the host only about 3 times in 10 (10/10, comments path)

**What happens.** "I get redness easily, will this cream irritate my skin?" on the DAON cream (whose documents say "Suitable for sensitive skin. Patch tested with no irritation reactions in our in-house test.") was sent 10 times, each in a new session, on revision 00015. The triage was the same every time (health, needs approval, HOST). Three times the answer composer used the suitability sentence and the draft verified, so the question reached the host list. Three times the composer returned `grounded: false` with no answer. Four times it answered with cautions only, and the draft verifier failed it ("does not answer the viewer's question"). Those seven went to the operator.

**Where.** The comments team's `answer_composer` and `draft_verifier` (prompts and agents). Session ids and agent calls are in Firestore `live-studio` (sessions `ses_01M4GHK…` to `ses_01M4GHPQ…`, 10/10).

**Status.** The user told the comments team that consistency is not guaranteed. Not ours to change.

## I-3. The viewer is told "The host will answer this on air" before the show starts (10/10, comments path)

**What happens.** After a demo reset the new session is `ready`, with no product on air. A HOST question with a verified draft gets reply status "host" (`logic/reply_status.py`), so the viewer reads "The host will answer this on air", but the host list only takes questions about the on-air product, so the host sees nothing until the show starts.

**Status.** Noted for the comments team.

## I-4. A red box clears on a retraction alone; requiring "retraction + replacement" is not reliable with the current judge (10/10, known limit)

**What happens.** The compliance judge clears a red box when the host's line makes clear, in any words, that the claim is withdrawn or corrected ("Sorry, I take that back", "I shouldn't have said that"). The host does not have to say the suggested replacement line too. Saying only an approved claim, with no retraction, can also clear it (seen twice on the cloud: "It helps keep skin hydrated for up to 24 hours..." cleared a "treats eczema and psoriasis" box).

**What was tried (D-436, 10/10).** A one-sentence rule "clear only when the line says the claim is not true or withdrawn; an approved claim alone does not clear it" (B), and one rephrase (B2), were checked against the current prompt on 13 cases x 3 runs each with Gemini 3.5 Flash-Lite at thinking LOW:

| Next line after the red box | Current | B | B2 |
|---|---|---|---|
| 7 natural retractions ("Sorry, it doesn't treat eczema", "Scratch that...", "Sorry, I take that back. <say_instead>") | 21/21 cleared | 21/21 | 21/21 |
| "It helps keep skin hydrated for up to 24 hours..." (approved claim, no retraction) | 0/3 cleared | 3/3 (wrong) | 0/3 |
| The suggested say_instead alone | 3/3 (wrong) | 3/3 (wrong) | 1/3 (wrong) |
| Repeat of the claim, a viewer question, another topic | not cleared | not cleared | not cleared |

Both B and B2 failed the pre-set kill rule (any wrong clear), so the prompt was left as it was. Cause: at thinking LOW the judge writes `fixed_by_this_line` with no reasoning step, and the example "take back + replacement = fixed" plus the say_instead text it is shown pull it toward "an approved claim means fixed". A harder rule ("retraction AND replacement both required") would be even less reliable.

**What was done instead.** The red box tells the host to read one full sentence: "Take it back, then say: 'Sorry, I take that back. <say_instead>'" (language-pack retraction phrase). Read as shown, it clears in every run.

**Options not taken (time and the 5 s latency line):** have the judge first quote the words of the line that withdraw the claim (empty quote = not cleared); thinking MEDIUM for the compliance judge; a stronger model for the clear decision only.

## I-5. A near-complete line ticks a multi-fact prompter point (10/10, open)

**What happens.** Point "1,000 mg of EPA and DHA in two softgels a day." ticks on "It has a thousand milligrams of EPA and DHA." (the dose "two softgels a day" is not said), 5/5 runs, with the context judge (Gemini 3.5 Flash-Lite, thinking MINIMAL).

**What was tried (probes, nothing shipped).**
- D-444 (shipped): "full meaning, a part alone does not tick". Fixed "1,000 mg." alone; this line passed once, then ticked again when the show had one more point.
- D-445 (killed): a bare-word sentence made MINIMAL tick more ("레몬향", "1,000 mg.").
- D-446: thinking MINIMAL / LOW / MEDIUM. LOW used 0 thinking tokens (same as MINIMAL). MEDIUM fixed this line but ticked the bare "레몬향"; context p95 4.7 s, too slow for switch and question hold.
- D-447 step 1 (Sonnet): same call, host words copied before the point id. This line still ticks 5/5; all other 15 lines right; switch and hold unchanged; p95 1.8 s.
- D-447 step 2 (GPT): a separate prompter-only call at MINIMAL. Same result on this line; all others right; p95 1.3 s.

**Left to try (needs the user):** the separate prompter-only call at thinking MEDIUM (nothing waits on it; an 8 s budget covers MEDIUM's p95 4.7 s), with the bare-word sentence. Or accept that a line stating amount and content but not the dose ticks.

**Update 10/11 (revision 00027, D-450 prompter judge at MEDIUM deployed).** Cloud check on the new product reads: "레몬향" alone no tick (fixed); "다음은 크림 보여드릴게요." switched to the cream by category (D-448b works); but "It has a thousand milligrams of EPA and DHA." ticked "Provides 1,000 mg of EPA and DHA in two softgels a day." again (the probe had 0/5; the point wording from the new onboarding differs, and the prompter call took 0.7 s, so MEDIUM did not think), and "레몬향 코팅이라 비린 맛이 거의 없어요." ticked "Features a lemon-scented coating, with 26 of 30 people in an in-house survey reporting no fishy aftertaste." without the survey number. Still open.

**Resolved 10/11 (D-455, revision 00028, main 30f4852).** The prompter judge runs on gemini-3.8-flash at thinking LOW with no deadline (D-454 probe: wrong 0/40, missed 0/63). Cloud check on the real Omega-3 read: the near-complete EPA line and the lemon line without the survey number no longer tick; the full lines tick; "레몬향" alone does not tick.

## I-1 status (10/11)
Resolved by the other team's PR #3 (34982cf): a screen without `?session` no longer joins a demo show.

## Sealed pool 8 measurement (10/11): issues found

One round on main 30f4852 (revision 00028): 6 new products (4 cosmetics on the ASEAN cosmetic claims guideline, 2 supplements on the HSA claims list), 504 host lines, voice A (Windows TTS Zira) through Chirp 3. Headline (overlap, stress and outside-the-prompter lines apart): detection 95.8% (115/120; compliance 66/66), false alerts 5.1% (17/336), wrong strongest alerts 7, alert p95 2.7 s. Two pass lines missed (false alerts < 1%, wrong strongest 0). Nothing was changed after the run. The examples below are made up; the sealed lines stay outside the repo.

### I-6. A product with several sizes or bundles gets one price on the prompter

**What happens.** The product read keeps one `list_price` and one `live_price` (`backend/app/api/products.py` `ProductInfo`), and a show builds one product with one price (`backend/app/onboarding/product_show.py`). A document with a 300 mL and a 500 mL bottle, each with its own price and a two-bottle bundle, shows only one pair of prices, without saying which size it belongs to. When the read cannot pick one (two pack sizes and a subscription price), it leaves both prices empty and the release is refused ("the product has no price").

**Effect.** The fact checker sees only that one price, so a host who says another size's right price ("the big bottle is $26") gets an orange "wrong price" alert. 4 of the 17 false alerts. A wrong price for another size can never be caught.

**Where to fix.** The product read and record (other team's onboarding) and the prompter/fact snapshot (live path). Not decided.

### I-7. A correct "more than $X" threshold line is flagged

**What happens.** The document says a gift or free shipping needs more than a set amount. The host says it right ("exactly $40 does not qualify yet, it has to be above $40"), and the fact checker shows an orange promo alert with the same threshold. 4 of the 17 false alerts.

### I-8. A claim the host rejects still gets an alert

**What happens.** The host reads a viewer's wrong claim and rejects it ("someone says it treats eczema, no, it doesn't"), or corrects a number in the next part of the same sentence, and an alert appears anyway (red for the rejected claim, orange for the corrected number). 4 of the 17 false alerts and 2 of the 7 wrong red alerts. The same class was seen in pools 6 and 7.

### I-9. The compliance judge raises red on lines that are only a wrong fact

**What happens.** A line that reverses a caution or overstates a test result ("you can take it even with a fish allergy", "dermatologist tested means allergy proof") gets a red regulation box, sometimes next to the right orange fact box. The line breaks the product's own document, not a clause of the regulation. 5 of the 7 wrong red alerts.

### I-10. STT returned no text for some audio

**What happens.** In the first STT pass of 636 short audio units, 9 came back with no final at all (5 of them in a row); a second pass of only those 9 gave text for all. On air these lines would be lost without any sign on the screen.

### Smaller items
- An old, discontinued size mentioned as old ("the 120 mL in that photo is the old bottle") is flagged as a wrong volume (2 false alerts).
- A test result explained in more detail than the prompter point (the share and the count of the same survey) is flagged (2).
- Fact lines whose value the prompter does not show (another size, a caution not in the points) are caught 2 of 18 times, as designed: the fact checker reads only what the prompter shows.
