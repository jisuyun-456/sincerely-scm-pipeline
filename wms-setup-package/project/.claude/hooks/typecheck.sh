#!/usr/bin/env bash
# TypeScript 타입 체크 — tsc --noEmit 자동 피드백 (D3)
# PostToolUse:Edit|Write 훅으로 실행됨
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""')

if [[ ! "$FILE_PATH" =~ \.(ts|tsx)$ ]]; then
  exit 0
fi

# tsconfig.json이 있는 프로젝트 디렉토리 탐색
PROJECT_DIR=$(dirname "$FILE_PATH")
while [[ "$PROJECT_DIR" != "/" ]] && [[ "$PROJECT_DIR" != "." ]]; do
  if [[ -f "$PROJECT_DIR/tsconfig.json" ]]; then
    cd "$PROJECT_DIR" && npx tsc --noEmit --pretty 2>&1 | head -20 || true
    break
  fi
  PROJECT_DIR=$(dirname "$PROJECT_DIR")
done

exit 0
