#!/bin/bash
# INSERT ONLY 원칙 위반 감지
# PreToolUse:Bash 훅으로 실행됨
INPUT=$(cat)
if echo "$INPUT" | grep -iE '(UPDATE|DELETE)\s.*(mat_document|stock_balance|inventory_transaction|accounting_entries)' > /dev/null 2>&1; then
  echo "BLOCK: INSERT ONLY 원칙 위반"
  echo "불변 원장 테이블은 UPDATE/DELETE 금지. 역분개(Storno)로 처리하세요."
  exit 1
fi
exit 0
