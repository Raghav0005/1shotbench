#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -n "${ANSERINI_JAR:-}" && -f "$ANSERINI_JAR" ]]; then
  JAR="$ANSERINI_JAR"
else
  JAR="$(find .anserini -maxdepth 1 -name 'anserini-*-fatjar.jar' -print 2>/dev/null | sort -V | tail -1)"
fi

test -n "$JAR"
test -f "$JAR"

mkdir -p artifacts/smoke
RUN_FILE="artifacts/smoke/run.cacm.bm25.txt"
EVAL_FILE="artifacts/smoke/eval.cacm.bm25.txt"

java -cp "$JAR" io.anserini.search.SearchCollection \
  -threads 1 \
  -index cacm \
  -topics cacm \
  -output "$RUN_FILE" \
  -hits 1000 \
  -bm25

java -cp "$JAR" io.anserini.eval.TrecEval \
  -c \
  -m map \
  -m P.30 \
  cacm \
  "$RUN_FILE" | tee "$EVAL_FILE"

grep -Eq '^map[[:space:]]+all[[:space:]]+0\.3123$' "$EVAL_FILE"
grep -Eq '^P_30[[:space:]]+all[[:space:]]+0\.1942$' "$EVAL_FILE"

echo "Smoke test OK with $JAR"
