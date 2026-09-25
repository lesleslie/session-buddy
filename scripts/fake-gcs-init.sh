#!/usr/bin/env bash
# scripts/fake-gcs-init-buckets.sh
# Create the canonical 4-bucket layout with lifecycle policy applied.
set -euo pipefail

ENDPOINT="${GCS_ENDPOINT:-http://127.0.0.1:4443}"
PROJECT="${GCS_PROJECT:-local-dev}"

for BUCKET in sessions-hot checkpoints-warm handoffs-cold archived; do
  echo "Creating bucket: $BUCKET"
  # fake-gcs-server accepts the GCS JSON API; gsutil from google-cloud-sdk works.
  gsutil -o "Credentials:anon" \
    -o "APIEndpoint:$ENDPOINT" \
    mb -p "$PROJECT" "gs://$BUCKET" 2>/dev/null || echo "  (already exists)"
done

# Lifecycle policy: Standard → Nearline (30d) → Coldline (90d) → Archive (365d)
cat > /tmp/lifecycle.json <<'EOF'
{
  "lifecycle": {
    "rule": [
      {"action": {"type": "SetStorageClass", "storageClass": "NEARLINE"},
       "condition": {"age": 30, "matchesStorageClass": ["STANDARD"]}},
      {"action": {"type": "SetStorageClass", "storageClass": "COLDLINE"},
       "condition": {"age": 90, "matchesStorageClass": ["NEARLINE"]}},
      {"action": {"type": "SetStorageClass", "storageClass": "ARCHIVE"},
       "condition": {"age": 365, "matchesStorageClass": ["COLDLINE"]}}
    ]
  }
}
EOF

for BUCKET in sessions-hot checkpoints-warm handoffs-cold archived; do
  echo "Applying lifecycle policy to $BUCKET"
  gsutil -o "Credentials:anon" -o "APIEndpoint:$ENDPOINT" \
    lifecycle set /tmp/lifecycle.json "gs://$BUCKET"
done

echo "Bucket layout:"
gsutil -o "Credentials:anon" -o "APIEndpoint:$ENDPOINT" ls
