#!/usr/bin/env bash
# Publish a customer-journey deck to a public GCS bucket so it can be
# shared via a stable URL. Run from the root of a prototype repo that
# contains a generated customer-journey/journey.html.
#
# Configure your bucket once:
#   export JOURNEY_BUCKET="gs://your-bucket-name"
#   export JOURNEY_HOST="https://storage.googleapis.com/your-bucket-name"
#
# Then publish:
#   bash publish.sh <project-name>

set -euo pipefail

BUCKET="${JOURNEY_BUCKET:-}"
HOST="${JOURNEY_HOST:-}"
SRC="customer-journey/journey.html"

if [ -z "$BUCKET" ] || [ -z "$HOST" ]; then
  echo "ERROR: JOURNEY_BUCKET and JOURNEY_HOST must be set." >&2
  echo "" >&2
  echo "Example:" >&2
  echo "  export JOURNEY_BUCKET=\"gs://my-prototype-decks\"" >&2
  echo "  export JOURNEY_HOST=\"https://storage.googleapis.com/my-prototype-decks\"" >&2
  exit 1
fi

if [ $# -lt 1 ]; then
  echo "Usage: publish.sh <project-name>" >&2
  echo "Run from the root of a prototype repo containing $SRC." >&2
  exit 1
fi

PROJECT="$1"

if [ ! -f "$SRC" ]; then
  echo "No $SRC found in $(pwd)." >&2
  echo "Generate the deck first with the customer-journey skill." >&2
  exit 1
fi

gcloud storage cp "$SRC" "$BUCKET/$PROJECT/journey.html" \
  --cache-control="no-cache, max-age=0" \
  --content-type="text/html; charset=utf-8"

echo ""
echo "Published: $HOST/$PROJECT/journey.html"
