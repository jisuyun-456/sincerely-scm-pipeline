#!/bin/bash
set -euo pipefail

# Remote (web) sessions only — local dev manages its own venv
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# Install core SCM pipeline dependencies
pip install -r requirements-autoresearch.txt pytest --quiet 2>/dev/null || \
  echo "[session-start] WARNING: pip install failed — network may be unavailable"

# Install graphifyy with MCP support
if ! python -c "import graphify" 2>/dev/null; then
  pip install "graphifyy[mcp]" --quiet 2>/dev/null || \
    echo "[session-start] WARNING: graphifyy install failed — MCP server will not be available"
fi

# Build or incrementally update the knowledge graph (skip if graphify not installed)
if python -c "import graphify" 2>/dev/null; then
  if [ -f graphify-out/graph.json ]; then
    graphify . \
      --obsidian-dir graphify-out/obsidian \
      --wiki \
      --update \
      2>/dev/null && echo "[session-start] graphify: incremental update complete" || true
  else
    graphify . \
      --obsidian-dir graphify-out/obsidian \
      --wiki \
      2>/dev/null && echo "[session-start] graphify: full build complete" || true
  fi
else
  echo "[session-start] graphify not available — skipping graph build"
fi
