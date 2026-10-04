# Deploying to Cloud Run (test deployment)

One test service in project `separk-cloocus` (and only there), behind IAP. Only `jaewoo@cloocus.com` may
open it for now.

| service | Cloud Run region | Speech-to-Text | Gemini | URL |
|---|---|---|---|---|
| `live-studio-us` | us-central1 | `us` (chirp_3) | `global` | https://live-studio-us-110085173686.us-central1.run.app |

Cloud Run runs next to Speech-to-Text, so the audio stream stays in the US. An earlier plan also had
`live-studio-sg` (asia-southeast1, near the viewers) to compare latency; it was dropped (user, 10/5).
Other Google resources (Firestore, Model Armor) go to us-central1 or a multi-region that contains it.

Why STT is `us` (checked 10/5): chirp_3 answers 403 "no longer generally available" in asia-southeast1,
asia-northeast1 and asia-south1 and works only in `us` and `eu`; chirp_2 in Singapore mishears product
words ("panthenol" as "penconazole"). gemini-3.5-flash-lite and gemini-3.8-flash answer only on the
`global` endpoint.

## Deploy

```sh
gcloud auth login                       # an account with Owner or Editor on separk-cloocus
gcloud components update                # `run deploy --iap` needs a recent SDK
deploy/cloudrun.sh                      # us-central1, IAP for jaewoo@cloocus.com
IAP_MEMBERS="user:a@example.com,user:b@example.com" deploy/cloudrun.sh   # more people (ask first)
```

The script:
- enables the APIs, builds the image with Cloud Build (no local Docker) into Artifact Registry;
- runs as the service account `live-studio-run` with only `roles/aiplatform.user` and `roles/speech.client`
  (add `roles/modelarmor.user` when Model Armor is switched on);
- deploys with `--no-allow-unauthenticated --iap`, grants the IAP service agent `run.invoker`, and gives
  each allowed member `iap.httpsResourceAccessor`.

## Settings and limits

- **Cold start, at most one instance:** `--min-instances=0`, so it scales to zero when idle and the first
  request after a pause waits for a start (open the page a minute before a show). `--max-instances=1` because sessions live in
  memory (`STORE=memory`). With more instances, the SSE stream, the audio WebSocket and the API calls of
  one session could land on different instances. `--session-affinity` is set but is best effort, so it
  does not replace the single instance. Firestore (`STORE=firestore`) removes this limit later.
- **CPU always allocated** (`--no-cpu-throttling`): the runtime keeps timers and background tasks (alert
  escalation, AI PD tick, pending posts) between requests. This bills only while an instance is up; with
  min-instances 0 it stops when idle (a session in memory is lost then).
- **Timeout 3600 s** so the SSE stream and the audio WebSocket stay open for a show.
- **Secrets:** none are needed. Google APIs use the service account (ADC); nothing is baked into the
  image (`.env` is excluded by `.dockerignore`). Future keys go to Secret Manager and are mounted with
  `--set-secrets`.
- **Demo tools** stay on (`DEMO_TOOLS_ENABLED=true`) for testing; `APP_ENV=cloud` turns them off by
  default otherwise.

## Check after a deploy

1. Open the URL, sign in with an allowed account; `/api/health` shows `llm: vertex`, `stt: google_v2`.
2. SSE through IAP: open the host and operator screens and start a demo session; events must arrive.
3. Audio WebSocket through IAP: turn the microphone on in the host screen; `mic` must reach "listening"
   and finals must appear.
4. Voice rehearsal: `BASE=<url> IAP_TOKEN=<token> node e2e/rehearsal-voice.mjs alerts`. A user's
   `gcloud auth print-identity-token` is refused ("Invalid JWT audience"): scripts need a token of a service
   account that has IAP access (`--impersonate-service-account=... --audiences=<url>`), which widens access
   and needs the user's approval. The browser flow is enough for a first check.
