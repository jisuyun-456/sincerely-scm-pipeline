#!/bin/bash
set -euo pipefail

cd "$CLAUDE_PROJECT_DIR"

# pip install: remote(web) 세션에서만 (로컬은 자체 venv 사용)
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
  pip install -r requirements-autoresearch.txt pytest --quiet 2>/dev/null || \
    echo "[session-start] WARNING: pip install failed — network may be unavailable"
  python -c "import graphify" 2>/dev/null || \
    pip install "graphifyy[mcp]" --quiet 2>/dev/null || \
    echo "[session-start] WARNING: graphifyy install failed — MCP server will not be available"
fi

# knowledge graph — git post-commit hook handles code-only rebuilds automatically (free, AST-only).
# For doc/config changes: run `/graphify . --update` in Claude Code (uses CC subscription tokens, no API key needed).
if [ -f graphify-out/graph.json ]; then
  echo "[session-start] graphify: graph.json ready ($(python -c "import json; g=json.load(open('graphify-out/graph.json')); print(f\"{len(g['nodes'])} nodes, {len(g['edges'])} edges\")" 2>/dev/null || echo 'size unknown'))"
else
  echo "[session-start] graphify: no graph.json found — run /graphify . in Claude Code to build"
fi
