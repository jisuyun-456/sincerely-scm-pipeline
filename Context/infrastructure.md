# 인프라/기술 스택 레퍼런스

> Claude가 Airtable API 호출 시 이 파일의 ID를 사용하세요. 외부에서 가져오거나 추측하지 마세요.

## Airtable — WMS Base

| 항목 | 값 |
|------|-----|
| Base ID | `appLui4ZR5HWcQRri` |
| Base 이름 | Sincerely WMS |

### 주요 테이블

| 테이블 | ID |
|--------|-----|
| movement | `tblwq7Kj5Y9nVjlOw` |
| order | `tblJslWg8sYEdCkXw` |
| material(parts-stock) | `tblaRpZstW10EwDlo` |
| sync_partner | `tblXx85u5gNzK7zTf` |
| sync_parts | `tblzJh0V4hdo4Xbvx` |

### movement 핵심 필드

| 필드명 | ID | 타입 |
|--------|-----|------|
| 이동목적 | `fldFRNxG1pNooEOC7` | singleSelect |
| 생성일자 | `fldDXUAF4JOORLJ2v` | dateTime |
| 실제입하일 | `flduN8khmYwdn7uVD` | date |
| 검수 status | `fldLpIDZBmq9jKYCh` | multilineText |
| 이동수량(변경) | `fld8i5WLz1UNmzvvB` | number |

### order 핵심 필드

| 필드명 | ID | 타입 |
|--------|-----|------|
| 입고예정일 | `fldjhWR2fGbp8hOn5` | date |
| 실제 입고일 | `fld7NwzcwyjoCldle` | date |
| 협력사 | `fldsofqeebz4UnCRN` | singleLineText |
| 표본 검수 결과 | `fldDlQdAT6L25QxEb` | singleSelect |
| 발주단계 | `fldBlcddggQhkp7dm` | singleSelect |

---

## Airtable — TMS Base

| 항목 | 값 |
|------|-----|
| Base ID | `app4x70a8mOrIKsMf` |
| Base 이름 | Sincerely TMS |

### TMS 주요 테이블 (GAP 17 테이블 완료, 2026-04-15)

| 테이블 | 용도 |
|--------|------|
| Shipment | 배송 건 마스터 |
| DeliveryEvent | 배송 이벤트/추적 |
| OTIF | 약속납기 실적 |
| Product | 제품/박스 마스터 (약 334종) |
| 배송SLA | SLA 리드타임 기준 |

### TMS 핵심 필드 (Product)

| 필드명 | ID | 타입 |
|--------|-----|------|
| 박스 당 CBM | `fld1ECU2hhnEurOef` | formula |

---

## 파이프라인/자동화

| 시스템 | 설명 |
|--------|------|
| GitHub Actions | TMS 주간 AutoResearch (매주 월요일) + WMS 주간 AutoResearch + 대시보드 cron (17:00 KST) |
| Railway | FastAPI PDF 생성 API (`api/app.py`) — 무료 마이그레이션 검토 중 (RAILWAY-MIG-01) |
| Vercel | sincerely-scm-dashboard (React) |
| Supabase | 대시보드 전용 스냅샷/집계 (SCM 운영 데이터 이중화 금지) |

---

## 로컬 Obsidian Vault (Windows)

| 항목 | 값 |
|------|-----|
| 경로 | `C:\Users\yjisu\Documents\ClaudeVault\` |
| 동기화 방식 | git pull (매주 월요일 09:15 KST, Windows Task Scheduler) |
| 동기화 대상 | `_AutoResearch/SCM/` → `ClaudeVault/_AutoResearch/SCM/` |

> **Cloud 세션에서는** `_AutoResearch/SCM/` 경로를 직접 사용합니다.
> Windows 로컬에서는 ClaudeVault 경로가 활성화됩니다.

---

## SAP 이동유형 레퍼런스

| 코드 | 의미 |
|------|------|
| 101 | 입고 (GR) |
| 201 | 출고 |
| 261 | 생산 출고 |
| 311 | 이전 |
| 601 | 납품 |
| 701 | 조정 |
| 122 | 반품 입고 |
| 551 | 폐기 |

---

## 회계 기준

- **K-IFRS** / 더존 아마란스10
- 계정코드: 1xxx(자산) ~ 5xxx(비용)
- **Immutable Ledger:** movement/mat_document INSERT ONLY — 정정은 Storno(역분개) 또는 보정 레코드로만
