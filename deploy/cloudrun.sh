#!/usr/bin/env bash
# Deploy Live Studio to Cloud Run with IAP (see docs/DEPLOY.md). Test deployments only.
#   deploy/cloudrun.sh                     # us-central1, next to Speech-to-Text "us" (user, 10/5)
# Builds the image and deploys a new revision; the one-time setup below is commented out (already done).
# Env: IAP_MEMBERS (comma list; default user:jaewoo@cloocus.com; used only by the commented IAP setup). The project is fixed to sample-uh (D-457; was ai-budiler-cup-uh-team-pjt, before that separk-cloocus).
set -euo pipefail

PROJECT="sample-uh"  # never another project
REGION="${1:-us-central1}"
case "$REGION" in
  us-central1) SERVICE="live-studio-us" ;;
  *) echo "unsupported region $REGION" >&2; exit 2 ;;
esac
IAP_MEMBERS="${IAP_MEMBERS:-user:jaewoo@cloocus.com}"
SA_NAME="live-studio-run"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
REPO="live-studio"
BUCKET="sample-uh-live-studio-onboarding"  # D-263: onboarding state (uploads, releases, law and brand packs)
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/app:$(git rev-parse --short HEAD)"
G="gcloud --project=${PROJECT}"

# ---- one-time setup (done for sample-uh by the user on 10/14: APIs incl. firestore and modelarmor, the service
# account and its roles, Firestore database live-studio (us-central1, native), the bucket, the image repository;
# uncomment for a new project) ----------------------------------------------------------------------------------
# echo "== APIs"
# $G services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
#   iap.googleapis.com aiplatform.googleapis.com speech.googleapis.com secretmanager.googleapis.com

# echo "== service account (least privilege: Vertex AI, Speech, Model Armor, Firestore, Trace)"
# $G iam service-accounts describe "$SA" >/dev/null 2>&1 || \
#   $G iam service-accounts create "$SA_NAME" --display-name="Live Studio Cloud Run"
# for role in roles/aiplatform.user roles/speech.client roles/modelarmor.user roles/datastore.user     roles/cloudtrace.agent; do
#   $G projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:${SA}" --role="$role" \
#     --condition=None >/dev/null
# done

# echo "== onboarding bucket (D-263: the source of truth for onboarding state; private, this service account only)"
# $G storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1 || \
#   $G storage buckets create "gs://${BUCKET}" --location="$REGION" --uniform-bucket-level-access \
#     --public-access-prevention
# $G storage buckets update "gs://${BUCKET}" --uniform-bucket-level-access --public-access-prevention >/dev/null
# $G storage buckets add-iam-policy-binding "gs://${BUCKET}" --member="serviceAccount:${SA}" \
#   --role=roles/storage.objectAdmin >/dev/null
# echo "== Vertex AI Search (viewer answers' evidence) and its data store bucket (approved product PDFs)"
# D-457: NOT yet in sample-uh. The comments team recreates the search app, its data store bucket and the Model Armor
# template live-studio-comments; then run these two with their bucket, and in the deploy below set
# MODEL_ARMOR_ENABLED=true,ANSWER_RETRIEVER=vertex_search,VERTEX_SEARCH_ENGINE_ID=<id>,VERTEX_SEARCH_GCS_BUCKET=<bucket>.
# $G projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:${SA}" --role=roles/discoveryengine.viewer \
#   --condition=None >/dev/null
# $G storage buckets add-iam-policy-binding gs://<data store bucket> --member="serviceAccount:${SA}" \
#   --role=roles/storage.objectAdmin >/dev/null
# ---- end of one-time setup -------------------------------------------------------------------------------------

echo "== image (Cloud Build; no local Docker needed)"
# one-time: the image repository
# $G artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 || \
#   $G artifacts repositories create "$REPO" --repository-format=docker --location="$REGION"
$G builds submit --tag "$IMAGE" .

echo "== deploy (scales to zero (cold start), at most one instance, session affinity)"
# GA "run deploy" (no gcloud beta component needed). IAP is turned on once after the first deploy (block below)
# and stays on: a deploy without --iap keeps the service's setting.
# min-instances 0: no always-on instance (user, 10/5); the first request after idle waits for a cold start.
# max-instances 1: a session's live state (timers, SSE, the audio WebSocket) runs in one process; Firestore
# (STORE=firestore, database live-studio, D-354) keeps it durable, but with more instances one session's calls
# could still land on different instances.
$G run deploy "$SERVICE" --region="$REGION" --image="$IMAGE" --service-account="$SA" \
  --no-allow-unauthenticated \
  --min-instances=0 --max-instances=1 --session-affinity --timeout=3600 --cpu=2 --memory=2Gi \
  --cpu-boost --no-cpu-throttling \
  --set-env-vars="APP_ENV=cloud,VIEWER_INPUT_ENABLED=true,GCP_PROJECT=${PROJECT},LLM_PROVIDER=vertex,LLM_LOCATION=global,STT_PROVIDER=google_v2,STT_LOCATION=us,STORE=firestore,FIRESTORE_DATABASE=live-studio,DEMO_TOOLS_ENABLED=true,MODEL_ARMOR_ENABLED=false,MODEL_ARMOR_LOCATION=us-central1,ONBOARDING_GCS_BUCKET=${BUCKET},STT_ENDPOINTING=STANDARD,SINGLE_MODEL=gemini-3.5-flash-lite,SINGLE_THINKING=LOW,SINGLE_FACTS_THINKING=LOW,FACT_PROMPT=v5,JUDGE_SEED=7,LLM_RETRY_ON_429_MS=500,ANSWER_RETRIEVER=local"
# D-457: MODEL_ARMOR_ENABLED=false and ANSWER_RETRIEVER=local until the comments team recreates the Model Armor template
# and the Vertex AI Search app in sample-uh (the one-time setup block above says how to turn them back on).

# ---- one-time, right after the first deploy to sample-uh: IAP on + access (needs the gcloud beta component) -------
# echo "== IAP on"
# $G beta run services update "$SERVICE" --region="$REGION" --iap
# echo "== IAP access"
# PROJECT_NUMBER="$($G projects describe "$PROJECT" --format='value(projectNumber)')"
# $G run services add-iam-policy-binding "$SERVICE" --region="$REGION" \
#   --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com" --role=roles/run.invoker
# IFS=',' read -ra MEMBERS <<< "$IAP_MEMBERS"
# for m in "${MEMBERS[@]}"; do
#   $G beta iap web add-iam-policy-binding --resource-type=cloud-run --service="$SERVICE" --region="$REGION" \
#     --member="$m" --role=roles/iap.httpsResourceAccessor
# done

URL="$($G run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')"
echo "== done: ${URL} (sign in with an allowed Google account)"
