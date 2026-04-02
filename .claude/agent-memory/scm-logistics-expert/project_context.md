---
name: Sincerely Project Context
description: 신시어리 물류팀 도메인 특성, Q1 핵심 이슈, 운영 환경 — scm-logistics-expert 컨텍스트
type: project
---

# 신시어리 물류팀 — SCM 전문가 컨텍스트

**Why:** 신시어리 프로젝트에 특화된 도메인 지식을 저장하여 매 세션 재학습 없이 즉시 적용
**How to apply:** 모든 SCM 분석/구현 작업 시 이 컨텍스트를 전제로 적용

## 비즈니스 특성

- B2B 커스텀 포장재 제조/배송 (프로젝트별 1회성 LOT 특성)
- 임가공 외주 (pkg_schedule/pkg_task로 관리)
- 창고 자가운영 (에이원 창고) + 1PL 혼용
  - 자가 기사: 조희선(38CBM/주), 이장훈(27CBM/주), 박종성(19CBM/주)
  - 외부: 로젠택배, 베스트원(퀵)

## Q1 2026 핵심 이슈 (근거 데이터)

| 이슈 | 수치 | 목표 |
|------|------|------|
| 검수 불량률 | 20.6% (2월 40.76% 스파이크) | ≤1% |
| 음수재고 | 331건 | 0건 |
| 미입하 누적 | 107건 미해결 | 0건 |
| CBM 달성률 | 기사별 27~57% | 80%+ |
| 운임 총액 | 56.9M원/Q1 | — |
| 자재 단가 미입력 | 8건 (추가사용액 금액화 불가) | 0건 |
| 1월 CBM 미집계 | Total_CBM 필드 미입력 | — |

## 주요 반복 불량 패턴

- 사각스티커(커스텀인쇄) — 1월/2월/3월 연속 반복. 동일 공급사 인쇄불량
- LOT 전량불량 패턴: 인쇄불량/시안오류/후가공불량/인쇄오염 4유형
- 근본 원인: 납품 전 샘플 승인 프로세스 없음, 시안 확정서 미수령

## Airtable 베이스 구조

- TMS: app4x70a8mOrIKsMf (13개 테이블)
- WMS: appLui4ZR5HWcQRri (14개 테이블 + 미운영 3개)
- 자재관리: appPeXyO6wrAa8x6L (20개 테이블)
- **이중화 이슈:** WMS.movement와 자재관리.movement 동시 운영 중

## 기술 환경

- NestJS 백엔드 (PM2 + ngrok, Railway 전환 예정)
- Supabase sap 스키마: mat_document (Shadow Ledger 운영 중)
- GitHub Actions + Python 파이프라인
- NocoDB/Metabase: 미적용 상태
