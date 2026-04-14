#!/usr/bin/env bash
# Auto-Format — 파일 수정 후 prettier 자동 실행 (D3/D4)
# PostToolUse:Edit|Write 훅으로 실행됨
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""')

if [[ -z "$FILE_PATH" ]] || [[ ! -f "$FILE_PATH" ]]; then
  exit 0
fi

# JS/TS/JSON/CSS 파일만 포맷
if [[ "$FILE_PATH" =~ \.(ts|tsx|js|jsx|json|css|scss)$ ]]; then
  npx prettier --write "$FILE_PATH" 2>/dev/null || true
fi

exit 0
