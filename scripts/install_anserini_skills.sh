#!/usr/bin/env bash
set -euo pipefail

repo_url="${1:-https://github.com/castorini/anserini.git}"
ref="${2:-master}"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/anserini-skills.XXXXXX")"

cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

git clone --depth 1 --filter=blob:none --sparse --branch "$ref" "$repo_url" "$tmp_dir/anserini"
cd "$tmp_dir/anserini"
git sparse-checkout set .agents/skills

cd - >/dev/null
mkdir -p .agents
rm -rf .agents/skills
cp -R "$tmp_dir/anserini/.agents/skills" .agents/skills

printf 'Installed Anserini skills into .agents/skills from %s @ %s\n' "$repo_url" "$ref"
