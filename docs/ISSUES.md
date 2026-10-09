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
