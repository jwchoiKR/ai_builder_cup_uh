# Deploying to Cloud Run (test deployment)

One test service in project `ai-budiler-cup-uh-team-pjt` (number 830408193168; and only there, D-289: moved from `separk-cloocus` on 10/6). It is public: no IAP,
no sign-in (user, 10/17, D-500).

| service | Cloud Run region | Speech-to-Text | Gemini | URL |
|---|---|---|---|---|
| `live-studio-us` | us-central1 | `us` (chirp_3) | `global` | https://live-studio-us-830408193168.us-central1.run.app (after the first deploy) |

Cloud Run runs next to Speech-to-Text, so the audio stream stays in the US. An earlier plan also had
`live-studio-sg` (asia-southeast1, near the viewers) to compare latency; it was dropped (user, 10/5).
Other Google resources (Firestore, Model Armor) go to us-central1 or a multi-region that contains it.

Why STT is `us` (checked 10/5): chirp_3 answers 403 "no longer generally available" in asia-southeast1,
asia-northeast1 and asia-south1 and works only in `us` and `eu`; chirp_2 in Singapore mishears product
words ("panthenol" as "penconazole"). gemini-3.5-flash-lite and gemini-3.8-flash answer only on the
`global` endpoint.

## Deploy

```sh
gcloud auth login                       # an account with Owner or Editor on ai-budiler-cup-uh-team-pjt
deploy/cloudrun.sh                      # us-central1, public
```

The script:
- enables the APIs, builds the image with Cloud Build (no local Docker) into Artifact Registry;
- runs as the service account `live-studio-run` with only `roles/aiplatform.user` and `roles/speech.client`
  (add `roles/modelarmor.user` when Model Armor is switched on);
- deploys with `--no-invoker-iam-check`: anyone with the URL can open it, without an `allUsers` binding
  (the same as the console setting; IAP is off).

## Settings and limits

- **Cold start, up to 3 instances:** `--min-instances=0`, so it scales to zero when idle and the first
  request after a pause waits for a start (open the page a minute before a show). `--max-instances=3` (user, 10/15;
  it was 1 from D-369). Show state is in Firestore (`STORE=firestore`) and `--session-affinity` keeps a browser on one
  instance, but a session's timers, SSE stream and audio WebSocket run in one process: the screens of one show can
  miss live events if they land on different instances. Affinity is best effort.
- **CPU always allocated** (`--no-cpu-throttling`): the runtime keeps timers and background tasks (alert
  escalation, AI PD tick, pending posts) between requests. This bills only while an instance is up; with
  min-instances 0 it stops when idle (a session in memory is lost then).
- **Timeout 3600 s** so the SSE stream and the audio WebSocket stay open for a show.
- **Secrets:** none are needed. Google APIs use the service account (ADC); nothing is baked into the
  image (`.env` is excluded by `.dockerignore`). Future keys go to Secret Manager and are mounted with
  `--set-secrets`.
- **Demo tools** stay on (`DEMO_TOOLS_ENABLED=true`) for testing; `APP_ENV=cloud` turns them off by
  default otherwise.

## Google resources (all in us-central1)

In `ai-budiler-cup-uh-team-pjt` (10/6): the APIs above, the Model Armor template `live-studio-comments` (same filters), and what `deploy/cloudrun.sh` creates (the service account, its roles, the onboarding bucket, Artifact Registry). Firestore, Vertex AI Search and the docs bucket are not recreated; the default config does not use them. The table below is the old project's setup (10/5).

| resource | name | used by |
|---|---|---|
| Firestore (Native) | database `live-studio` | `STORE=firestore` later. A named database, because the project's `(default)` location is tied to the App Engine app in asia-northeast3 |
| Model Armor template | `live-studio-comments` | comment screening (D-125): prompt injection and jailbreak MEDIUM_AND_ABOVE, malicious URLs, RAI (hate, harassment, sexual, dangerous) HIGH |
| Cloud Storage | `gs://separk-cloocus-live-studio-docs` (`products/`, `policy/` PDFs) | private, uniform access; the service account can only read |
| Cloud Trace | API enabled | spans later |

`live-studio-run` has `roles/datastore.user`, `roles/modelarmor.user`, `roles/cloudtrace.agent` and
`roles/storage.objectViewer` on the bucket.

Model Armor measured from Korea: 280-370 ms per comment (a few over 500 ms, so they would be unscreened);
from us-central1 it should be well under the 500 ms limit. "Developer mode" role-play wording passed the
MEDIUM_AND_ABOVE jailbreak filter in one try; the triage prompt still treats comments as untrusted data.

## Check after a deploy

1. Open the URL (no sign-in); `/api/health` shows `llm: vertex`, `stt: google_v2`.
2. SSE: open the host and operator screens and start a demo session; events must arrive.
3. Audio WebSocket: turn the microphone on in the host screen; `mic` must reach "listening"
   and finals must appear.
4. Voice rehearsal: `BASE=<url> node e2e/rehearsal-voice.mjs alerts`.

Checked 10/5 (then behind IAP): `/api/health` ok (`llm: vertex`, `stt: google_v2`); SSE `200
text/event-stream` with session, transcript and alert events; the audio WebSocket reached "listening" in
280 ms.
