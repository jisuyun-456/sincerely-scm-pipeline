# PreToolUse Hook — git-guardrails (AUDIT-X11-A)

**Date:** 2026-05-16
**Origin:** Phase 2 6-Layer audit Cross-layer #11 — Hook 커버리지 8 lifecycle 누락 중 가장 가치 큰 첫 항목
**Skill leveraged:** `git-guardrails` (`~/.claude/skills/git-guardrails/SKILL.md`)
**Reference:** oh-my-claudecode `pre-tool-enforcer.mjs` (20 hooks × 11 events 비교)

## Context

현재 `~/.claude/settings.json` 에 PreToolUse 훅 없음. Stop 훅이 git status warn만 함 — *blocking이 아님*. 위험 명령(`git push --force`, `git reset --hard`, `--no-verify`, `git clean -f`)은 사용자/Claude 둘 다 사고로 실행 가능.

Phase 1 lessons/global.md (line 19-22)도 이를 인지 — "사용자 입력 lesson에 `git push --force`, `rm -rf`, `--no-verify` 등 dangerous 표현 sanitization rejection". 그러나 *런타임 명령 차단*은 없음 — lesson 저장 시점만 검사.

## Decisions (locked)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Scope** | Global (`~/.claude/settings.json`) | Git 안전성은 모든 프로젝트 공통. SCM_WORK·STOCK_WORK·사이드 프로젝트 모두 보호 |
| **Matcher** | `Bash` (모든 Bash 호출 intercept) | 파일 편집은 안전, Bash 명령만 위험 |
| **Block list** | git-guardrails 스킬 기본 + `--no-verify` 명시 | YAGNI — 더 추가 시 false positive 위험 |
| **Bypass** | 없음 (Phase 1) | "옵션 우회"는 곧 본질 무력화. 사용자가 명시적으로 정말 필요하면 hook 일시 disable. |
| **Phase 1 integration** | 차단 발생 시 stderr만 (events.jsonl 미통합) | YAGNI — 첫 PR은 최소 변경. 추후 `runtime.capability.missing` 통합 검토 |

### Block list (확정)

**git-guardrails 스킬 기본:**
- `git push` (모든 variant)
- `git reset --hard`
- `git clean -f` / `git clean -fd`
- `git branch -D`
- `git checkout .` / `git restore .`

**추가 (Phase 1 lessons 정렬):**
- 모든 `--no-verify` flag (hook 우회 시도)
- 모든 `--no-gpg-sign` flag (signing 우회)
- `rm -rf` (특히 luminal path: `/`, `~/`, `*/`)

스크립트 customization 단계에서 추가.

## Architecture

```
[Claude wants to run Bash command]
    ↓
[PreToolUse hook fires: ~/.claude/hooks/block-dangerous-git.sh]
    ├─ stdin: tool_input JSON ({"tool_input":{"command":"..."}})
    ├─ Check: command matches block pattern?
    │   ├─ YES → stderr "BLOCKED: ..." + exit 2 → Claude sees deny
    │   └─ NO  → exit 0 → Bash 진행
    ↓
[Bash 실행 or BLOCKED]
```

**훅 위치:** `~/.claude/hooks/block-dangerous-git.sh`
**settings.json 매핑:**
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "~/.claude/hooks/block-dangerous-git.sh"}]
      }
    ]
  }
}
```

기존 settings.json hooks 보존 — `PreToolUse` 키만 새로 추가 (다른 키 영향 없음).

## Implementation Steps

1. ✅ Skill 호출 (이 spec 작성)
2. Fetch `block-dangerous-git.sh` 스크립트 from upstream
3. 저장: `~/.claude/hooks/block-dangerous-git.sh` + `chmod +x`
4. Script customize: `--no-verify`, `--no-gpg-sign`, `rm -rf` 패턴 추가
5. `~/.claude/settings.json` 의 `hooks.PreToolUse` 배열에 entry 추가 (기존 키 보존)
6. Verification: `echo '{"tool_input":{"command":"git push origin main"}}' | bash <script>` → exit 2 + BLOCKED 메시지

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| False positive — 합법적 `git push` 시도 차단 | 사용자가 인지하고 hook 일시 disable 또는 메인 Claude가 user에게 confirm 요청 |
| Hook script 자체 버그 → 모든 Bash 호출 차단 | exit 0 default (실패 시 통과). 스크립트 syntax error 시 hook silent skip |
| Windows 환경 .sh 실행 | Git Bash via Claude Code Bash tool 사용 — `.sh` shebang `#!/bin/bash` 동작 확인 |
| `rm -rf` 정당한 사용 (예: tmp 디렉토리 정리) | 패턴 정밀화 — `rm -rf /` `rm -rf ~/` `rm -rf *` 같은 destructive root 패턴만 차단 |

## Out of Scope (YAGNI — 후속)

| 제외 | 이유 |
|------|------|
| `runtime.capability.missing` event 발행 통합 | 첫 PR 최소 변경; 추후 1 line addition |
| Hook bypass mechanism (`--allow-dangerous`) | 우회 옵션이 곧 무력화 — 명시적 hook disable이 더 명확 |
| 다른 위험 도구(npm publish, docker push) | scope creep — 본 audit 항목은 git only |
| Slack/Notion 알림 (차단 발생 시) | YAGNI; stderr 로 충분 |
| Per-project block list override | 글로벌 정책 일관성 우선 |

## Verification

1. 스크립트 다운로드 후 chmod +x 적용 확인
2. settings.json `hooks.PreToolUse` 존재 + 다른 4 hooks (Stop/Notification/PostToolUse/SessionStart) 보존 확인
3. `echo '{"tool_input":{"command":"git push origin main"}}' | bash ~/.claude/hooks/block-dangerous-git.sh; echo "exit: $?"` → exit 2 + BLOCKED 출력
4. `echo '{"tool_input":{"command":"git status"}}' | bash ~/.claude/hooks/block-dangerous-git.sh; echo "exit: $?"` → exit 0 (passthrough)
5. 다음 세션에서 실제 차단 동작 확인 (Claude가 차단 메시지 받음)

## Files Modified

- NEW: `~/.claude/hooks/block-dangerous-git.sh` (downloaded + customized)
- MODIFIED: `~/.claude/settings.json` (`hooks.PreToolUse` 추가)
- NEW (this spec): `docs/superpowers/specs/2026-05-16-pretool-git-guardrails-design.md`

## Backlog Status After Implementation

- `AUDIT-X11-A` → **status: done** (`.claude/feature_list.json`)
- `AUDIT-X11-B` (SubagentStop) — 다음 작업
- `AUDIT-X11-C` (PreCompact) — 다음 작업
