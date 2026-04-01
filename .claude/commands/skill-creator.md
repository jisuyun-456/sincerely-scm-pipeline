# /skill-creator — 새 스킬 생성

새 스킬을 만들 때 아래 절차를 따르세요.
글로벌 `superpowers:writing-skills`를 기반으로 SCM 프로젝트 컨벤션을 적용합니다.

## 1. 스킬 유형 결정

| 유형 | 저장 위치 | 예시 |
|------|----------|------|
| SCM/물류 절차 | `.claude/skills/scm/` | 이동유형 결정, SCOR 프로세스 |
| 회계/세무 절차 | `.claude/skills/accounting/` | 분개 생성, 기간마감 |
| 기술/DB 절차 | `.claude/skills/tech/` | 정합성 검증, 쿼리 최적화 |
| 디자인/UI 절차 | `.claude/skills/design/` | WCAG 감사 |
| PM/기획 절차 | `.claude/skills/pm/` | MECE 분해, 리스크 레지스터 |
| 프로젝트 명령 | `.claude/commands/` | 세션 루틴, 마이그레이션 |

## 2. 스킬 파일 골격

```markdown
---
name: {skill-id}
description: 한 줄 설명 (트리거 키워드 포함)
---

# {스킬명}

## 언제 사용
- 트리거 조건 명시

## Step 1: {첫 번째 단계}
...

## Step N: {마지막 단계}
...

## 출력 형식
...
```

## 3. 명명 규칙

- 파일명: `kebab-case.md` (예: `sap-movement.md`)
- name 필드: 파일명과 동일
- description: 동사로 시작 (예: "SAP 이동유형 결정 및 역분개 처리")

## 4. 검증

스킬 생성 후 `Skill` 도구로 호출 테스트:
```
Skill tool → skill: "{skill-id}"
```

## 5. superpowers 활용

복잡한 스킬이면 먼저 글로벌 스킬 참고:
```
Skill tool → skill: "superpowers:writing-skills"
```
