#!/bin/bash
# Run graphify on this repo and export to Obsidian vault format + wiki
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$REPO_ROOT/graphify-out"

cd "$REPO_ROOT"

# First run: full build. Subsequent runs: incremental update only for changed files.
if [ -f "$OUT_DIR/graph.json" ]; then
  graphify . \
    --obsidian-dir "$OUT_DIR/obsidian" \
    --wiki \
    --update
else
  graphify . \
    --obsidian-dir "$OUT_DIR/obsidian" \
    --wiki
fi

echo "graphify complete — outputs at $OUT_DIR"
echo "  graph.json      : queryable knowledge graph"
echo "  graph.html      : interactive visualization"
echo "  GRAPH_REPORT.md : god nodes + community summary"
echo "  obsidian/       : Obsidian vault markdown (sync to ClaudeVault)"
echo "  wiki/           : agent-crawlable markdown wiki"
