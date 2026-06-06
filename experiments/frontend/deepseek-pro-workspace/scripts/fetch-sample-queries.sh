#!/usr/bin/env bash
#
# fetch-sample-queries.sh — Extract sample queries from the MS MARCO passage
# dev topic set and write them as a TypeScript array for the frontend.
#
# Prerequisites:
#   - ANSERINI_JAR set (source .env or run install-anserini.sh first)
#
# Usage:
#   bash scripts/fetch-sample-queries.sh
#
set -euo pipefail

# ---- Load env ----
if [ -f .env ]; then
  set -a; source .env; set +a
fi

if [ -z "${ANSERINI_JAR:-}" ] || [ ! -f "${ANSERINI_JAR:-}" ]; then
  echo "ERROR: ANSERINI_JAR not set or file not found."
  echo "Run scripts/install-anserini.sh first."
  exit 1
fi

echo "==> Fetching msmarco-v1-passage.dev topics..."

# TopicsRegistry --get outputs the topics as formatted text.
# We extract the "title" field lines.
TOPICS_OUTPUT=$(java -cp "$ANSERINI_JAR" io.anserini.cli.TopicsRegistry --get msmarco-v1-passage.dev 2>&1)

# Extract query strings from the output.
# The TopicsRegistry output format varies by version; we try to extract text
# after "title:" or similar patterns.
QUERIES=$(echo "$TOPICS_OUTPUT" | grep -oP '(?:title|Title|query|Query)["\s:]*\K[^"]+' | head -50 || true)

if [ -z "$QUERIES" ]; then
  echo "WARNING: Could not parse queries from TopicsRegistry output."
  echo "Raw output (first 500 chars):"
  echo "$TOPICS_OUTPUT" | head -20
  echo ""
  echo "Using the existing sample queries in src/lib/sampleQueries.ts instead."
  echo "To update them manually, inspect the TopicsRegistry output above."
  exit 1
fi

# Format as TypeScript array
echo "export const SAMPLE_QUERIES: string[] = ["
while IFS= read -r line; do
  # Escape double quotes and backslashes
  escaped=$(echo "$line" | sed 's/\\/\\\\/g; s/"/\\"/g')
  echo "  \"$escaped\","
done <<< "$QUERIES"
echo "];"
echo ""
echo "==> Copy the array above into src/lib/sampleQueries.ts"
echo "    (replace the existing SAMPLE_QUERIES array)."
