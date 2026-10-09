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
