#!/usr/bin/env bash
# Deploy Live Studio to Cloud Run with IAP (see docs/DEPLOY.md). Test deployments only.
#   deploy/cloudrun.sh asia-southeast1     # service live-studio-sg
#   deploy/cloudrun.sh us-central1         # service live-studio-us
# Env: PROJECT (fixed to separk-cloocus), IAP_MEMBERS (comma list, default the owner's account).
set -euo pipefail

PROJECT="separk-cloocus"  # never another project
REGION="${1:?region: asia-southeast1 or us-central1}"
case "$REGION" in
  asia-southeast1) SERVICE="live-studio-sg" ;;
  us-central1) SERVICE="live-studio-us" ;;
  *) echo "unsupported region $REGION" >&2; exit 2 ;;
esac
IAP_MEMBERS="${IAP_MEMBERS:-user:cloocus.gtc2@gmail.com}"
SA_NAME="live-studio-run"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
REPO="live-studio"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/app:$(git rev-parse --short HEAD)"
G="gcloud --project=${PROJECT}"

echo "== APIs"
$G services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  iap.googleapis.com aiplatform.googleapis.com speech.googleapis.com secretmanager.googleapis.com

echo "== service account (least privilege: Vertex AI user, Speech client)"
$G iam service-accounts describe "$SA" >/dev/null 2>&1 || \
  $G iam service-accounts create "$SA_NAME" --display-name="Live Studio Cloud Run"
for role in roles/aiplatform.user roles/speech.client; do
  $G projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:${SA}" --role="$role" \
    --condition=None >/dev/null
done

echo "== image (Cloud Build; no local Docker needed)"
$G artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 || \
  $G artifacts repositories create "$REPO" --repository-format=docker --location="$REGION"
$G builds submit --tag "$IMAGE" .

echo "== deploy (IAP, one warm instance, session affinity)"
# max-instances 1: sessions live in memory (STORE=memory); with more instances SSE, the audio
# WebSocket and API calls of one session could land on different instances.
$G beta run deploy "$SERVICE" --region="$REGION" --image="$IMAGE" --service-account="$SA" \
  --no-allow-unauthenticated --iap \
  --min-instances=1 --max-instances=1 --session-affinity --timeout=3600 --cpu=2 --memory=2Gi \
  --cpu-boost --no-cpu-throttling \
  --set-env-vars="APP_ENV=cloud,GCP_PROJECT=${PROJECT},LLM_PROVIDER=vertex,LLM_LOCATION=global,STT_PROVIDER=google_v2,STT_LOCATION=us,STORE=memory,RETRIEVER=local,DEMO_TOOLS_ENABLED=true"

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
