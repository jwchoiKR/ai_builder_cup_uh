#!/usr/bin/env bash
# Deploy Live Studio to Cloud Run (see docs/DEPLOY.md).
#   deploy/cloudrun.sh                     # us-central1, next to Speech-to-Text "us" (user, 10/5)
# Builds the image and deploys a new revision; the one-time setup below is commented out (already done).
# The project is fixed to ai-budiler-cup-uh-team-pjt (back from sample-uh on 10/15 after its Gemini block was lifted; D-457 had moved it to sample-uh).
set -euo pipefail

PROJECT="ai-budiler-cup-uh-team-pjt"  # never another project
REGION="${1:-us-central1}"
case "$REGION" in
  us-central1) SERVICE="live-studio-us" ;;
  *) echo "unsupported region $REGION" >&2; exit 2 ;;
esac
SA_NAME="live-studio-run"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
REPO="live-studio"
BUCKET="ai-budiler-cup-uh-team-pjt-live-studio-onboarding"  # D-263: onboarding state (uploads, releases, law and brand packs)
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/app:$(git rev-parse --short HEAD)"
G="gcloud --project=${PROJECT}"

# ---- one-time setup (done for this project, and for sample-uh by the user on 10/14: APIs incl. firestore and modelarmor, the service
# account and its roles, Firestore database live-studio (us-central1, native), the bucket, the image repository;
# uncomment for a new project) ----------------------------------------------------------------------------------
# echo "== APIs"
# $G services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
#   aiplatform.googleapis.com speech.googleapis.com secretmanager.googleapis.com

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

echo "== deploy (scales to zero (cold start), up to 3 instances, session affinity)"
# GA "run deploy" (no gcloud beta component needed). Public, no IAP (user, 10/17, D-500): --no-invoker-iam-check
# matches the console setting (invoker IAM check off, no allUsers binding).
# min-instances 0: no always-on instance (user, 10/5); the first request after idle waits for a cold start.
# max-instances 3 (user, 10/15; was 1 from D-369): session affinity keeps a browser on one instance and Firestore
# (STORE=firestore, database live-studio, D-354) keeps show state durable. A session's timers, SSE and audio
# WebSocket still run in one process, so the screens of one show can miss live events if they land on different
# instances.
$G run deploy "$SERVICE" --region="$REGION" --image="$IMAGE" --service-account="$SA" \
  --no-invoker-iam-check \
  --min-instances=0 --max-instances=3 --session-affinity --timeout=3600 --cpu=2 --memory=2Gi \
  --cpu-boost --no-cpu-throttling \
  --set-env-vars="APP_ENV=cloud,VIEWER_INPUT_ENABLED=true,GCP_PROJECT=${PROJECT},LLM_PROVIDER=vertex,LLM_LOCATION=global,STT_PROVIDER=google_v2,STT_LOCATION=us,STORE=firestore,FIRESTORE_DATABASE=live-studio,DEMO_TOOLS_ENABLED=true,MODEL_ARMOR_ENABLED=true,MODEL_ARMOR_LOCATION=us-central1,ONBOARDING_GCS_BUCKET=${BUCKET},STT_ENDPOINTING=STANDARD,SINGLE_MODEL=gemini-3.5-flash-lite,SINGLE_THINKING=LOW,SINGLE_FACTS_THINKING=LOW,FACTS_MODEL=gemini-3.8-flash,FACT_PROMPT=v5,JUDGE_SEED=7,LLM_RETRY_ON_429_MS=500,ANSWER_RETRIEVER=vertex_search,VERTEX_SEARCH_ENGINE_ID=ai-budiler-cup-uh-search_1791461058419,VERTEX_SEARCH_GCS_BUCKET=ai-budiler-cup-uh-data-source"
# Model Armor and Vertex AI Search exist in this project (the comments team set them up); sample-uh had neither (D-457).

URL="$($G run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')"
echo "== done: ${URL}"
