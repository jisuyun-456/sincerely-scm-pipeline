#!/usr/bin/env bash
# 변경 파일 관련 테스트 자동 실행 (D3 기술 아키텍트)
# PostToolUse:Edit|Write 훅으로 실행됨
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""')

if [[ ! "$FILE_PATH" =~ \.(ts|tsx|js|jsx)$ ]]; then
  exit 0
fi

# 테스트 파일 자체 수정이면 해당 파일 실행
if [[ "$FILE_PATH" =~ \.(spec|test)\.(ts|tsx|js|jsx)$ ]]; then
  npx jest "$FILE_PATH" --passWithNoTests 2>&1 | tail -15 || true
  exit 0
fi

# 소스 파일이면 관련 테스트 찾아서 실행
BASE_NAME=$(basename "$FILE_PATH" | sed 's/\.[^.]*$//')
SPEC_PATTERN="${BASE_NAME}.spec"
npx jest --testPathPattern="$SPEC_PATTERN" --passWithNoTests 2>&1 | tail -15 || true

exit 0
