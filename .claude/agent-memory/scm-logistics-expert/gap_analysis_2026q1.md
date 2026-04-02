---
name: AS-IS Gap Analysis 2026-Q1
description: 신시어리 TMS/WMS Airtable 구조와 SAP 표준 대비 누락 항목 전체 목록 및 우선순위 (2026-04-02 브레인스토밍 결과)
type: project
---

# AS-IS Gap Analysis — 2026 Q1 브레인스토밍 결과

**Why:** Q1 음수재고 331건, 불량률 20.6%, 미입하 107건, CBM 달성률 27~57% 이슈 해결을 위한 SAP 표준 Gap 분석
**How to apply:** feature_list.json 업데이트 시, 아래 항목 기준으로 우선순위 적용

## TMS 누락 항목

| ID | 항목 | SAP T-Code | Airtable 가능 | 우선순위 |
|----|------|------------|:------------:|---------|
| T-TMS-01 | ASN 입하예정 테이블 신설 | VL32N | 가능 | Critical |
| T-TMS-02 | 운임정산 + 프로젝트 배분 | /SCMTMS/FRSE | 가능 | High |
| T-TMS-06 | 파트너 성과 스코어카드 | ME61 | 가능 | High |
| T-TMS-05 | Last-mile 추적 자동화 | Event Mgmt | 부분가능 | Medium |
| T-TMS-03 | 배차계획 (수동 적재최적화) | Load Building | 부분가능 | Medium |
| T-TMS-04 | Multi-stop 루트최적화 | VSR | 불가 | Low (TO-BE) |

## WMS 누락 항목

| ID | 항목 | SAP T-Code | Airtable 가능 | 우선순위 |
|----|------|------------|:------------:|---------|
| W-NEW-01 | movement_type 강제화 (W-5 연계) | LT0A/EWM | 부분가능 | High |
| W-NEW-02 | Wave Management | /SCWM/WAVE | 가능 | High |
| W-NEW-03 | Putaway Strategy (수동) | /SCWM/SRULE | 부분가능 | Medium |
| W-NEW-04 | Handling Unit / 패킹명세서 | HUPAST | 가능 | Medium |
| W-NEW-05 | 실사 운영화 (기존 3개 테이블) | MI01/MI04/MI07 | 가능 | High |
| W-NEW-06 | LOT/Batch 관리 | MSC1N | 가능 | High |
| W-NEW-07 | Cross-docking | /SCWM/XDCK | 부분가능 | Low |

## Airtable 절대 불가 항목 (Supabase TO-BE 필수)

- 음수재고 DB 레벨 방어 (CHECK constraint)
- FIFO/FEFO 자동 LOT 선택 (출고 시 알고리즘)
- 재고원장 불변성 (INSERT ONLY, DELETE 불가)
- 기간마감 불가역 처리
- 실시간 재고 잔량 보장 (Row-level locking)
- 자동 Putaway 결정 (용량/규칙 기반)

## 통합 실행 페이즈 (2026-04-02 확정)

| 페이즈 | 항목 | 비고 |
|--------|------|------|
| PHASE 0 (즉시) | W-NEW-01, T-TMS-01 | 의존성 없음, 병렬 착수 |
| PHASE 1 (3~6주) | W-NEW-05, W-NEW-06, W-1, W-NEW-02 | 음수재고+불량률 동시 공격 |
| PHASE 2 (7~12주) | T-TMS-06, T-TMS-02, W-2, W-3 | 프로세스 고도화 |
| PHASE 3 (13~20주) | W-5, W-4, T-TMS-03, T-TMS-05, W-NEW-03, W-NEW-04, W-6 | 운영 최적화 |
| PHASE 4 (20주+) | T-TMS-04, W-NEW-07, Supabase TO-BE | TO-BE 전환 |

## Critical Path

W-NEW-01 (movement_type 강제화) → W-NEW-05 (실사 운영화) + W-NEW-06 (LOT 관리) + T-TMS-01 (ASN) → W-1 (불량코드) + W-NEW-02 (Wave) → T-TMS-06 (파트너 스코어카드) + W-2 (NCR) → Supabase TO-BE 불변원장

## 자재관리 베이스 통합 방향

- WMS.movement = Master (공식 재고원장)
- 자재관리.movement = Read-only 아카이브로 전환
- 이중 기표가 음수재고 331건 주요 원인으로 추정
- 단일화 경로: Airtable WMS.movement → NestJS → Supabase sap.mat_document
