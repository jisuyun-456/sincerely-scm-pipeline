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

# knowledge graph 빌드 (로컬·remote 공통)
if python -c "import graphify" 2>/dev/null; then
  if [ -f graphify-out/graph.json ]; then
    graphify . --obsidian-dir graphify-out/obsidian --wiki --update 2>/dev/null \
      && echo "[session-start] graphify: incremental update complete" || true
  else
    graphify . --obsidian-dir graphify-out/obsidian --wiki 2>/dev/null \
      && echo "[session-start] graphify: full build complete" || true
  fi
else
  echo "[session-start] graphify not available — run: pip install 'graphifyy[mcp]'"
fi
