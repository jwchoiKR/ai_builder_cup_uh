#!/usr/bin/env bash
# Deploy Live Studio to Cloud Run with IAP (see docs/DEPLOY.md). Test deployments only.
#   deploy/cloudrun.sh                     # us-central1, next to Speech-to-Text "us" (user, 10/5)
# Env: IAP_MEMBERS (comma list; default user:jaewoo@cloocus.com). The project is fixed to ai-budiler-cup-uh-team-pjt (D-289; was separk-cloocus).
set -euo pipefail

PROJECT="ai-budiler-cup-uh-team-pjt"  # never another project
REGION="${1:-us-central1}"
case "$REGION" in
  us-central1) SERVICE="live-studio-us" ;;
  *) echo "unsupported region $REGION" >&2; exit 2 ;;
esac
IAP_MEMBERS="${IAP_MEMBERS:-user:jaewoo@cloocus.com}"
SA_NAME="live-studio-run"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
REPO="live-studio"
BUCKET="ai-budiler-cup-uh-team-pjt-live-studio-onboarding"  # D-263: onboarding state (uploads, releases, law and brand packs)
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/app:$(git rev-parse --short HEAD)"
G="gcloud --project=${PROJECT}"

echo "== APIs"
$G services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  iap.googleapis.com aiplatform.googleapis.com speech.googleapis.com secretmanager.googleapis.com

echo "== service account (least privilege: Vertex AI, Speech, Model Armor, Firestore, Trace)"
$G iam service-accounts describe "$SA" >/dev/null 2>&1 || \
  $G iam service-accounts create "$SA_NAME" --display-name="Live Studio Cloud Run"
for role in roles/aiplatform.user roles/speech.client roles/modelarmor.user roles/datastore.user     roles/cloudtrace.agent; do
  $G projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:${SA}" --role="$role" \
    --condition=None >/dev/null
done

echo "== onboarding bucket (D-263: the source of truth for onboarding state; private, this service account only)"
$G storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1 || \
  $G storage buckets create "gs://${BUCKET}" --location="$REGION" --uniform-bucket-level-access \
    --public-access-prevention
$G storage buckets update "gs://${BUCKET}" --uniform-bucket-level-access --public-access-prevention >/dev/null
$G storage buckets add-iam-policy-binding "gs://${BUCKET}" --member="serviceAccount:${SA}" \
  --role=roles/storage.objectAdmin >/dev/null

echo "== image (Cloud Build; no local Docker needed)"
$G artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 || \
  $G artifacts repositories create "$REPO" --repository-format=docker --location="$REGION"
$G builds submit --tag "$IMAGE" .

echo "== deploy (IAP, scales to zero (cold start), at most one instance, session affinity)"
# min-instances 0: no always-on instance (user, 10/5); the first request after idle waits for a cold start.
# max-instances 1: a session's live state (timers, SSE, the audio WebSocket) runs in one process; Firestore
# (STORE=firestore, database live-studio, D-354) keeps it durable, but with more instances one session's calls
# could still land on different instances.
$G beta run deploy "$SERVICE" --region="$REGION" --image="$IMAGE" --service-account="$SA" \
  --no-allow-unauthenticated --iap \
  --min-instances=0 --max-instances=1 --session-affinity --timeout=3600 --cpu=2 --memory=2Gi \
  --cpu-boost --no-cpu-throttling \
  --set-env-vars="APP_ENV=cloud,GCP_PROJECT=${PROJECT},LLM_PROVIDER=vertex,LLM_LOCATION=global,STT_PROVIDER=google_v2,STT_LOCATION=us,STORE=firestore,FIRESTORE_DATABASE=live-studio,RETRIEVER=local,DEMO_TOOLS_ENABLED=true,MODEL_ARMOR_ENABLED=true,MODEL_ARMOR_LOCATION=us-central1,ONBOARDING_GCS_BUCKET=${BUCKET},VERIFY_MODE=lean,STT_ENDPOINTING=STANDARD,JUDGE_ARM=single,SINGLE_MODEL=gemini-3.5-flash-lite,SINGLE_THINKING=LOW,SINGLE_FACTS_THINKING=LOW,FACT_PROMPT=v5,FACT_MODE=prompter,JUDGE_SEED=7,QUESTION_HOLD=true,LLM_RETRY_ON_429_MS=500,SWITCH_ARM_NAME=false,CORRECTION_CHECK=judge,QUALIFIER_ADDON=false,JUDGE_PRODUCTS=all,CORRECTION_HANDLES=true,SWITCH_MODE=immediate"

echo "== IAP access"
PROJECT_NUMBER="$($G projects describe "$PROJECT" --format='value(projectNumber)')"
$G run services add-iam-policy-binding "$SERVICE" --region="$REGION" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com" --role=roles/run.invoker
IFS=',' read -ra MEMBERS <<< "$IAP_MEMBERS"
for m in "${MEMBERS[@]}"; do
  $G beta iap web add-iam-policy-binding --resource-type=cloud-run --service="$SERVICE" --region="$REGION" \
    --member="$m" --role=roles/iap.httpsResourceAccessor
done

URL="$($G run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')"
echo "== done: ${URL} (sign in with an allowed Google account)"
