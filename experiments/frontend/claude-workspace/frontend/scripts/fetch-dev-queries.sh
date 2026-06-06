#!/usr/bin/env bash
# Regenerate frontend/data/msmarco-passage-dev-queries.json from the Anserini
# TopicsRegistry. Requires ANSERINI_JAR to be set and `jq` to be on PATH.
set -euo pipefail

if [[ -z "${ANSERINI_JAR:-}" || ! -f "${ANSERINI_JAR}" ]]; then
  echo "ANSERINI_JAR is not set or does not point to a file." >&2
  echo "Run install-anserini-fatjar first and export ANSERINI_JAR." >&2
  exit 1
fi

OUT="$(cd "$(dirname "$0")/.." && pwd)/data/msmarco-passage-dev-queries.json"
mkdir -p "$(dirname "$OUT")"

RAW="$(mktemp)"
trap 'rm -f "$RAW"' EXIT

java -cp "$ANSERINI_JAR" io.anserini.cli.TopicsRegistry \
  --get msmarco-v1-passage.dev > "$RAW"

jq '[to_entries[] | {id: .key, text: .value.title}]' "$RAW" > "$OUT"

echo "Wrote $(jq 'length' "$OUT") queries to $OUT"
