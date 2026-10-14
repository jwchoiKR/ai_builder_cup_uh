#!/usr/bin/env bash
# Print a one-hour IAP token for scripts (voice driver): a JWT signed by the test service account
# live-studio-driver, through your gcloud user (needs roles/iam.serviceAccountTokenCreator on it; no key file).
# Direct IAP on Cloud Run refuses ordinary ID tokens ("Invalid JWT audience"); a signed JWT with the
# service URL as audience works. Usage: IAP_TOKEN=$(deploy/iap-token.sh) BASE=<url> node e2e/rehearsal-voice.mjs
set -euo pipefail
URL="${1:-https://live-studio-us-699711909838.us-central1.run.app}"
SA="live-studio-driver@sample-uh.iam.gserviceaccount.com"  # D-457: create it in sample-uh first
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
now="$(date +%s)"
printf '{"iss":"%s","sub":"%s","aud":"%s/*","iat":%d,"exp":%d}' "$SA" "$SA" "$URL" "$now" "$((now + 3600))" > "$tmp/claim.json"
gcloud iam service-accounts sign-jwt --iam-account="$SA" "$tmp/claim.json" "$tmp/token.jwt" >/dev/null 2>&1
cat "$tmp/token.jwt"
