#!/usr/bin/env bash
# 브랜치 보호 — force push, main/master 직접 push 차단 (D3 기술 아키텍트)
# PreToolUse:Bash 훅으로 실행됨
INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# force push 차단
if echo "$CMD" | grep -qE "git\s+push\s+.*(--force|-f)"; then
  echo "BLOCK: force push 금지" >&2
  exit 2
fi

# main/master 직접 push 차단
if echo "$CMD" | grep -qE "git\s+push\s+.*\b(main|master)\b"; then
  BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
  if [[ "$BRANCH" == "main" || "$BRANCH" == "master" ]]; then
    echo "BLOCK: main/master 직접 push 금지. feature 브랜치를 사용하세요." >&2
    exit 2
  fi
fi

exit 0
