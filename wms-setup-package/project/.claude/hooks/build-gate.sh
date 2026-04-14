#!/usr/bin/env bash
# 빌드 게이트 — 세션 종료 시 빌드 통과 필수 (D3 기술 아키텍트)
# Stop 훅으로 실행됨
INPUT=$(cat)

# 무한루프 방지 (필수!)
ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [[ "$ACTIVE" == "true" ]]; then
  exit 0
fi

# package.json이 있는 프로젝트에서만 실행
if [[ ! -f "package.json" ]]; then
  exit 0
fi

# build 스크립트가 있으면 빌드 검증
if grep -q '"build"' package.json 2>/dev/null; then
  echo "=== Build Gate: npm run build ===" >&2
  if npm run build 2>&1 | tail -5; then
    echo "Build OK" >&2
  else
    echo "Build FAILED" >&2
    exit 2
  fi
fi

exit 0
