#!/usr/bin/env bash
# INSERT ONLY 원칙 위반 감지 (D1 SCM + D2 회계)
# PreToolUse:Bash 훅으로 실행됨
INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# 불변 원장 테이블 UPDATE/DELETE 차단
PROTECTED="mat_document|stock_balance|inventory_transaction|accounting_entries|period_close"
if echo "$CMD" | grep -iE "(UPDATE|DELETE)\s.*($PROTECTED)" > /dev/null 2>&1; then
  echo "BLOCK: INSERT ONLY 원칙 위반" >&2
  echo "불변 원장은 UPDATE/DELETE 금지. 역분개(Storno)로 처리하세요." >&2
  exit 2
fi

# 마감 기간 직접 INSERT 경고 (D2 회계)
if echo "$CMD" | grep -iE "INSERT\s+INTO\s+.*period_close" > /dev/null 2>&1; then
  echo "WARNING: period_close 직접 INSERT 감지. 기간 마감은 서비스 로직으로만 처리하세요." >&2
fi

exit 0
