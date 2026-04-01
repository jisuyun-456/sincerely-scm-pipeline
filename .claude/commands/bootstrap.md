---
description: 새 프로젝트에 전문가 에이전트 팀 초기화. /bootstrap으로 5전문가+오케스트레이터 자동 생성.
---

# 전문가 에이전트 팀 부트스트랩

새 프로젝트에 범용 전문가 에이전트 팀을 설정합니다.

## 1. 프로젝트 분석

```bash
# 기술 스택 감지
ls package.json requirements.txt pyproject.toml Cargo.toml go.mod pom.xml 2>/dev/null
# 기존 .claude 구조 확인
ls -la .claude/ 2>/dev/null
ls -la .claude/agents/ 2>/dev/null
```

## 2. 에이전트 생성 (6개)

`.claude/agents/` 디렉토리에 아래 에이전트를 생성:

1. `scm-logistics-expert.md` — D1 SCM/물류 (APICS CSCP+CPIM+CLTD, SCOR, SAP, GS1)
2. `tax-accounting-expert.md` — D2 세무/회계 (K-IFRS, SAP FI/CO, 더존 아마란스10)
3. `tech-architect.md` — D3 기술 (시스템 설계, 코딩, 디버깅, DevOps)
4. `frontend-design-expert.md` — D4 디자인 (UI/UX, WCAG 2.1 AA, 디자인 시스템)
5. `project-manager.md` — D5 PM (BCG, McKinsey, PMBOK, Agile)
6. `orchestrator.md` — 복수 도메인 조율

각 에이전트는 글로벌 CLAUDE.md의 **에이전트 작성 표준**을 따르되,
프로젝트 컨텍스트(기술 스택, 비즈니스 도메인)에 맞게 커스터마이즈합니다.

## 3. 프로젝트 CLAUDE.md 갱신

프로젝트 루트 CLAUDE.md에 에이전트 팀 라우팅 표를 추가합니다.

## 4. 스킬 디렉토리 생성

프로젝트에 필요한 스킬만 선택적으로 생성:
- **모든 프로젝트:** `tech/` (기술 스킬)
- **물류/SCM 프로젝트:** `scm/`, `accounting/`
- **웹 프로젝트:** `design/`
- **관리 프로젝트:** `pm/`

## 5. 완료 보고

생성된 파일 목록과 각 에이전트의 역할을 요약 출력합니다.
