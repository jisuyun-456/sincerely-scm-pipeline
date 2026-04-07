# TMS SAP 보완 7개 테이블 — 프로세스·필드·데이터 연결 상세 분석

> 작성일: 2026-04-03  
> 목적: TMS 완료 테이블을 SAP TM 관점으로 이해하고 운용하기 위한 참조 문서

---

## 전체 테이블 관계 지도

```
[고객/프로젝트]
      │
      ▼
[배송SLA] ← 구간유형+배송방식별 목표 기준
      │ 적용
      ▼
[Shipment] ─────────────────────────────────┐
  (출하 마스터)                              │
      │ 1:N 이벤트                          │ 1:1 OTIF
      ▼                                    ▼
[배송이벤트]                              [OTIF]
  (배송 상태 이력)                    (정시/완전납품 KPI)
      │                                    │
      │ 이상 발생                          │ 미달성시
      ▼                                    ▼
[배송클레임]                         [운임단가]
  (파손/분실/오배송)               (CBM 구간별 단가 → 비용계산)
                                          │
                                          ▼
      ┌─────────────────────────────[정산관리]
      │                            (프로젝트별 물류비 집계)
      ▼
[택배추적로그]
  (택배사 원본 추적 데이터)
```

**Shipment 테이블이 허브**: 7개 테이블이 모두 Shipment에 연결됨

---

## 1. Shipment — 중심 테이블 (7개 연결 필드)

> **SAP 대응:** Freight Order + Outbound Delivery

Shipment는 허브 테이블. 7개 신규 테이블 모두 이 테이블에서 파생됨.

### 7개 테이블 연결 필드 (Shipment에 추가된 것들)

| 필드명 | 필드ID | 타입 | SAP 대응 | 설명 |
|--------|--------|------|---------|------|
| 약속납기일 | `fldyYIfBhhu7sEX1P` | date | Requested Delivery Date | OTIF 측정 기준일. 고객에게 약속한 완료일 |
| 약속수량 | `fldJ5czWvSJ1NMQmW` | number | Planned Qty | OTIF 기준 수량 |
| POD_확인일시 | `fldNPH5xLdYevknfZ` | dateTime | POD Timestamp | 고객 수령 확인 시점 |
| POD_수령자명 | `fld6OTjF9Tw6GdwJb` | text | POD Signer | 실제 수령인 성명 |
| POD_불일치여부 | `fldtNZnDMf10cbxkQ` | checkbox | POD Discrepancy | 수량/품목 불일치 발생 여부 |
| 배차일지_매칭키 | `fldoQV2ksYHLuLZvE` | formula | - | `출하확정일_배송파트너명` 자동 생성 |
| **OTIF** | `fldQEpW6QI8Qg3nDn` | link | - | → OTIF 테이블 |
| **배송이벤트** | `fldtS7VtbyXaAKTl7` | link | - | → 배송이벤트 테이블 |
| **배송클레임** | `fldS2mABpzmtudiPc` | link | - | → 배송클레임 테이블 |
| **정산관리** | `fldgl8LtobJeZThxI` | link | - | → 정산관리 테이블 |
| **택배추적로그** | `fldHGqWyi0aqwNve7` | link | - | → 택배추적로그 테이블 |

---

## 2. OTIF 테이블 (tbl4WfEuGLDlqCTQH)

> **SAP 대응:** TM Delivery Performance KPI  
> **데이터:** 348건 | **관계:** Shipment 1:1

### 역할
"이 Shipment, 제 시간에 약속한 수량 전부 배달했나?" 를 측정하는 성적표.  
SAP에서는 Freight Order별로 OT(On Time) + IF(In Full) 두 가지를 측정 → 곱해서 OTIF Score.

### 자동화
**Trigger:** Shipment.발송상태_TMS = "출하완료"  
**Action:** OTIF 레코드 자동 생성 (현재 운영 중)

### 필드 전체

| 필드명 | 필드ID | 타입 | 역할 |
|--------|--------|------|------|
| OTIF_ID | `fld8FO4vDkVFOlYJd` | text | 고유 ID (예: OTIF-20260320-001) |
| Shipment | `fldGwqw0LSIoa824Z` | link | 측정 대상 Shipment (1:1 연결) |
| **약속납기일** | `fldtUxptEKXh7Nz8z` | date | 고객 약속일 (Shipment에서 복사) |
| **실제배송일** | `fldLKPPns5EXUJZ8y` | date | 실제 배송 완료일 |
| **약속수량** | `fldUrB85pNM9dfXqZ` | number | 약속한 출하 수량 |
| **실제수량** | `fldG3t15IWrpE6glP` | number | 실제 배송된 수량 |
| 미달성사유 | `fldrumMRlIKSjMVrv` | select | OTIF 미달성 시 사유 선택 |
| 비고 | `fldEgDaBpe9LUZIjR` | text | 자유 메모 |
| **On_Time** | `fldoUQOue0umGJ2xk` | formula | `실제배송일 ≤ 약속납기일` → TRUE/FALSE |
| **In_Full** | `fldiFhyU1k9YsnoGh` | formula | `실제수량 ≥ 약속수량` → TRUE/FALSE |
| **OTIF_Score** | `fldRrWN15iV9BoToc` | formula | `On_Time AND In_Full` → 달성/미달성 |
| 납기차이일 | `fldZJD4YRYg8Mr6yi` | formula | `실제배송일 - 약속납기일` (음수=조기배송) |
| 수량차이 | `fldpxJ7BJEefewj4X` | formula | `실제수량 - 약속수량` (음수=부족배송) |

### 운용 방법 (SAP식)
1. Shipment 발송 완료 → OTIF 레코드 자동 생성 (약속납기일·약속수량 자동 복사)
2. 배송 완료 후 → 실제배송일, 실제수량 입력
3. On_Time / In_Full / OTIF_Score 자동 계산
4. 월간 집계 → `배송파트너.월간_OTIF달성률` rollup으로 파트너 성과 평가

### 현재 상태 & 주의사항
- 백필 데이터: 약속납기일 = 출하확정일 (proxy). 실제 고객 약속일 아님
- 실제 약속납기일 입력 시작 → On_Time 값 재계산 필요
- 현재 On_Time 모두 TRUE (proxy여서 항상 일치)

---

## 3. 배송이벤트 테이블 (tblQyuAW30yf21WEf)

> **SAP 대응:** TM Event Management  
> **데이터:** 349건 | **관계:** Shipment 1:N

### 역할
Shipment 상태 변화를 **이벤트 로그**로 기록. Shipment의 `발송상태_TMS` 단일 필드와 달리, 모든 상태 변화 이력을 시간순으로 쌓는다.  
SAP에서는 "Delivery Expected", "Goods Picked Up", "Delivered" 등 각 단계마다 타임스탬프 이벤트 생성.

### 필드 전체

| 필드명 | 필드ID | 타입 | 역할 |
|--------|--------|------|------|
| 이벤트ID | `fld1gqsJsUYlxir5p` | text | 고유 ID (예: EVT-20260320-001) |
| Shipment | `fldIAAYK8bfiVl5iv` | link | 대상 Shipment (N:1 — 하나의 Shipment에 여러 이벤트) |
| **이벤트유형** | `fldbBqodeAJhAQATW` | select | 픽업완료/허브도착/배송중/배송완료/배송실패/반품 |
| **이벤트일시** | `fld9IsE0lC5p1Pf1a` | dateTime | 이벤트 발생 시점 (타임스탬프) |
| 위치 | `fldXROvKThnHpYdnr` | text | 이벤트 발생 장소 (터미널명, 지점명 등) |
| 택배사참조번호 | `fld94m3XkGveiRUav` | text | 운송장번호 등 택배사 참조값 |
| 기록자 | `fldgd0nnt9frwdXWr` | collaborator | 이벤트 기록 담당자 |
| 비고 | `fldU2WzrW5ZeGRsXC` | text | 메모 |
| 증빙사진 | `fldn5w4hDiWRV0jO4` | attachments | 배송 증빙 사진 |

### 이벤트유형 선택지 (SAP Event Type)
```
픽업완료 → 허브도착 → 배송중 → 배송완료
                        ↘ 배송실패 → 반품
```

### 운용 방법 (SAP식)
1. 배송 단계마다 이벤트 레코드 하나씩 추가 (INSERT ONLY 원칙)
2. 이벤트유형 선택 + 이벤트일시 기록
3. 택배 기사 현장에서 사진 첨부 가능
4. Shipment에서 `배송이벤트 (lookup)` → 전체 이력 조회

### 현재 상태 & 주의사항
- 백필: 이벤트유형=배송완료, 이벤트일시=출하확정일 09:00 (중간 이벤트 없음)
- 향후: 픽업완료/허브도착 등 중간 이벤트도 추가하면 완전한 배송 가시성 확보 가능
- 하나의 Shipment에 N개 레코드 연결 가능 (1:N)

---

## 4. 운임단가 테이블 (tblQA1ev9fjbowUoP)

> **SAP 대응:** TM Freight Cost Calculation / Rate Tables  
> **데이터:** 15건 | **관계:** 배송파트너 → Shipment 예상운임 계산에 활용

### 역할
"이 Shipment, 얼마짜리 운임?" 을 계산하기 위한 단가 마스터.  
배송파트너(기사/택배사)별, 구간유형별, CBM 구간별로 기본운임 + 초과분 단가를 저장.

### 필드 전체

| 필드명 | 필드ID | 타입 | 역할 |
|--------|--------|------|------|
| 단가코드 | `fldgEBCocAOMPSw4j` | text | 고유 코드 (예: RT-JHS-METRO-01) |
| 배송파트너 | `fldgc1e6CEmIj6II1` | link | 적용 배송파트너 |
| **구간유형** | `fld2y2g5SJMCKJJl8` | select | 수도권/지방/도서산간/당일퀵 |
| **CBM_최소** | `fld4DQRC3X3JPmRjP` | number | CBM 구간 시작값 |
| **CBM_최대** | `fldh6UTE9G3osg2mp` | number | CBM 구간 끝값 |
| **기본운임** | `fld8UyM9hPOOX6pTU` | currency | 기본 요금 (KRW) |
| CBM당_추가운임 | `fldFT8nO6QrXWcJh1` | currency | CBM 초과분 단가 |
| 상하차비_포함 | `fldKYXMLQ7SwuPBeA` | checkbox | 상하차비 포함 여부 |
| **유효시작일** | `fldcN7yDOW91S6YwG` | date | 단가 유효 시작일 |
| 유효종료일 | `fldoMTwX2LRHIbaR4` | date | 단가 유효 종료일 (NULL=무기한) |
| 비고 | `fld5NzvGg0jryCiX4` | text | 메모 |

### 현재 마스터 데이터 구성 (15건)
```
기사 3명 × 4구간 = 12건
  - 박종성(RT-JJS-*): 수도권/중부/경상/기타
  - 이장훈(RT-LJH-*): 수도권/중부/경상/기타
  - 조희선(RT-JHS-*): 수도권/중부/경상/기타

택배사 3개 = 3건
  - 로젠(RT-LOGEN-*)
  - 고고엑스(RT-GOGOX-*)
  - 베스트원(RT-BEST1-*)
```

### 운임 계산 방식
```
예상운임 = 기본운임 + (Shipment.Total_CBM - CBM_최소) × CBM당_추가운임
          (Shipment의 CBM이 해당 구간에 해당하는 단가 행 선택)
```

### 운용 방법 (SAP식)
1. 단가 변경 시 → 기존 행 유효종료일 설정 + 새 행 추가 (이력 보존)
2. 지방/도서산간 노선 발생 시 → 해당 단가 행 추가
3. Shipment에서 예상운임 자동계산 formula에서 이 테이블 참조

---

## 5. 배송SLA 테이블 (tblbPC6z0AsbvcVxJ)

> **SAP 대응:** TM Service Level Agreement  
> **데이터:** 9건 | **관계:** OTIF 목표값 기준

### 역할
"어떤 구간, 어떤 방식으로 보낼 때 OTIF 목표를 몇 %로 볼 건가?" 기준표.  
SAP에서는 고객/계약별로 SLA를 설정하고 OTIF 측정 기준으로 사용.

### 필드 전체

| 필드명 | 필드ID | 타입 | 역할 |
|--------|--------|------|------|
| SLA코드 | `fld0QyXN98nIjEAAr` | text | 고유 코드 |
| **구간유형** | `fldOcAzLmHw3gb6Gr` | select | 수도권/지방/도서산간/당일퀵 |
| **배송방식** | `fldpm7IsG1gZrvsfG` | select | 기사직배/택배/퀵 |
| 목표배송시간 | `fldvcDfTULpnaDxHu` | number | 배송 목표 시간 (시간 단위) |
| **목표배송일수** | `fldlZ0INaM3CNidcD` | number | 배송 목표 일수 |
| **OTIF목표** | `fldFM7JiHtp9Akucc` | percent | 해당 구간/방식의 OTIF 달성 목표 (%) |
| 패널티조건 | `fldsM0LPvL4HQd36R` | text | SLA 미달성 시 패널티 조건 |
| 유효시작일 | `fldkYxw4ARpbB7Rem` | date | SLA 적용 시작일 |
| 비고 | `fldxO34xbsl1YSkoL` | text | 메모 |

### 현재 SLA 구성 (9건)
```
구간유형 4개 × 배송방식 3개 조합
  수도권 × 기사직배 → OTIF목표 98%, 목표배송일수 1
  수도권 × 택배     → OTIF목표 90%, 목표배송일수 2
  수도권 × 퀵       → OTIF목표 95%, 목표배송일수 1
  지방   × 기사직배 → OTIF목표 85%, 목표배송일수 2
  지방   × 택배     → OTIF목표 80%, 목표배송일수 3
  ... (9개 조합)
```

### 운용 방법 (SAP식)
1. Shipment 생성 시 → 구간유형 + 배송방식 기반으로 해당 SLA 매칭
2. OTIF 계산 시 → 이 테이블의 OTIF목표와 실제 OTIF_Score 비교
3. 계약/시즌 변경 시 → 유효시작일 설정 후 새 행 추가

---

## 6. 배송클레임 테이블 (tblIZ9kco1QDpUz0u)

> **SAP 대응:** TM Claims Management  
> **데이터:** 0건 (구조 완성, 실제 발생 시 수동 입력)  
> **관계:** Shipment, 배송파트너

### 역할
배송 중 파손/분실/오배송 발생 시 체계적으로 기록·추적.  
운송사 성과평가 근거 데이터 + 보상 처리 이력.

### 필드 전체

| 필드명 | 필드ID | 타입 | 역할 |
|--------|--------|------|------|
| 클레임번호 | `fldaRZL1Ry7fU4P0V` | text | 고유 번호 (예: CLM-20260320-001) |
| **클레임유형** | `fldL2x3aqDQ4qjlD6` | select | 파손/분실/오배송/지연/수량부족 |
| **발생일** | `fldiNGNqgmQH1MFB7` | date | 클레임 발생일 |
| 접수일 | `fldekjQXkNuHT4fNP` | date | 클레임 접수일 |
| 피해품목 | `fldpgZCMRBUW2MySm` | text | 피해 발생 품목명 |
| 피해수량 | `fldLJxXa59adIQFfz` | number | 피해 수량 |
| **피해금액** | `fldxBT0XumwS7u3Kk` | currency | 피해 금액 (KRW) |
| 보상방법 | `fld3fgEYoBbVI4n0G` | select | 현금보상/재발송/교환/환불 |
| **보상금액** | `fldk6eb7QZar8tzBR` | currency | 실제 보상 금액 |
| **처리상태** | `fldevAs6IBB0rN2MY` | select | 접수/조사중/보상완료/종결 |
| 증빙사진 | `fldDnLED7No4pW0PC` | attachments | 파손/피해 사진 |
| 담당자 | `fldoxAcWfi13D5S8f` | collaborator | 처리 담당자 |
| 완료일 | `fldehqO23gjCjHezh` | date | 클레임 완료일 |
| 재발방지대책 | `fldGEr64oLBnsoFmg` | text | 원인 분석 + 재발방지 |
| **Shipment** | `fldS0DB6PsCSL1QJu` | link | 해당 Shipment 연결 |
| **배송파트너** | `fldm96CqoNw0pS5ut` | link | 책임 배송파트너 연결 |

### 운용 방법 (SAP식)
1. 클레임 발생 → 클레임번호 부여 + 발생일/유형 즉시 입력
2. Shipment, 배송파트너 링크
3. 증빙사진 첨부
4. 조사 → 보상방법/금액 결정 → 처리상태 업데이트
5. 배송파트너.클레임건수 / 파손건수 필드는 수동 집계로 업데이트

---

## 7. 정산관리 테이블 (tblf0BClxZtnQfOJL)

> **SAP 대응:** TM Freight Settlement / Cost Allocation  
> **데이터:** 2건 (3월/4월) | **관계:** Shipment (다수)

### 역할
월 단위로 프로젝트별 물류비를 집계해서 정산.  
운송비 + 상하차비 + 포장비 + 기타 → 총물류비 자동계산 + 물류손익.

### 필드 전체

| 필드명 | 필드ID | 타입 | 역할 |
|--------|--------|------|------|
| 정산번호 | `fldJunT77bCP9whiP` | text | 고유 번호 (예: STL-202603) |
| 프로젝트명 | `fldxDTSvmXb6onsG6` | text | 정산 대상 프로젝트명 |
| **운송비** | `fldSzZzCWyHbn1uwQ` | currency | 운송 비용 합계 |
| **상하차비** | `fldrJc1nV9g0ug1yp` | currency | 상하차 비용 합계 |
| 포장비 | `fldFJErA5zoGVyNgq` | currency | 포장 비용 합계 |
| 기타비용 | `fldG4gktwftp6e6Lz` | currency | 기타 비용 |
| **물류매출** | `fld10T2VhPsqqckUN` | currency | 고객 청구 물류매출 |
| **정산상태** | `fldywI0JMLAm918NX` | select | 정산대기/정산완료/확인중 |
| 정산월 | `flddGuJoD8kRVsknO` | text | 정산 월 (예: 2026-03) |
| 세금계산서번호 | `fldoWBSTU4RTNOMSI` | text | 세금계산서 발행 번호 |
| 비고 | `fldPoSJvrmxePsCJz` | text | 메모 |
| **Shipment** | `fldzLobm7U7vGACR1` | link | 정산 대상 Shipment 다수 연결 |
| **총물류비** | `fldJpFmBEsLXhVti6` | formula | 운송비+상하차비+포장비+기타비용 자동합산 |
| **물류손익** | `fldPMliTVOOwLM5FY` | formula | 물류매출 - 총물류비 |

### 운용 방법 (SAP식)
1. 월말 → 해당 월 Shipment 전체 선택 → Shipment 링크
2. 비용 집계 (운송비, 상하차비 등) 입력
3. 물류매출 입력 → 물류손익 자동계산
4. 정산완료 → 세금계산서번호 입력

### 현재 상태 & 주의사항
- 3월 정산: 8,553,350원 (200건 기준 — 실제 349건 기준 재집계 필요)
- 4월 정산: 0원 (미정산)
- Shipment.물류비(합계) rollup으로도 집계 가능

---

## 8. 택배추적로그 테이블 (tblonyqcHGa5V5zbj)

> **SAP 대응:** TM Carrier Tracking Integration  
> **데이터:** 73건 (로젠택배 전량) | **관계:** Shipment

### 역할
택배사(CJ/한진/로젠/우체국)의 배송 이벤트 원본 데이터를 그대로 보존.  
배송이벤트 테이블이 내부 표준화 이벤트라면, 택배추적로그는 외부 택배사 원본 그대로.

### 필드 전체

| 필드명 | 필드ID | 타입 | 역할 |
|--------|--------|------|------|
| 추적ID | `fldNEjERsz8qEJDnw` | text | 고유 ID |
| **택배사** | `fldDDhjUKPZVgrYH0` | select | CJ/한진/로젠/우체국/고고엑스 |
| **운송장번호** | `fldvzKlwRSlkNCRiA` | text | 택배사 운송장번호 |
| **추적상태** | `flduWediJYFSaZlbh` | select | 접수/집화/이동중/배송중/배송완료/미배달 |
| **추적일시** | `fldnxRdyJOkMqRbL6` | dateTime | 해당 상태 발생 시각 |
| 추적위치 | `flduAgLKleH9TJdk4` | text | 택배 터미널/지점명 |
| 수령인 | `fldZaINSTgVJvJGGB` | text | 수령인 성명 |
| 비고 | `fldGM0bpzA89eLrlU` | text | 메모 |
| **Shipment** | `fldmxi2cX7Ozl54Tj` | link | 해당 Shipment 연결 |

### 배송이벤트 vs 택배추적로그 차이

| 구분 | 배송이벤트 | 택배추적로그 |
|------|-----------|------------|
| 대상 | 모든 배송방식 | 택배사 포함 배송 |
| 데이터 출처 | 내부 수동 입력 | 택배사 API 원본 |
| 이벤트유형 | 표준화 (픽업완료 등) | 택배사 고유 상태값 |
| 용도 | OTIF/SLA 분석 | 고객 CS, 분쟁 증거 |

### 운용 방법 (SAP식)
1. 택배 발송 → 운송장번호 입력 후 택배사 API로 추적상태 조회
2. 조회 결과 → 레코드 추가 (추적상태 변화마다 새 레코드)
3. 배송완료 확인 → OTIF 실제배송일 업데이트
4. Shipment.운송장 조회 링크(로젠) 필드로 직접 조회 가능

### 현재 상태 & 주의사항
- 로젠택배 운송장(숫자 8~15자리)만 73건 백필
- CJ/한진/우체국 운송장은 아직 미입력
- 향후 자동화: 운송장번호 입력 → Zap/스크립트로 API 조회 자동화 가능

---

## 전체 프로세스 흐름 (SAP TM 관점)

```
STEP 1. 배송 요청
배송요청 테이블 → 배송방식/구간유형 결정
→ 배송SLA 테이블에서 OTIF 목표 확인 (예: 수도권 기사직배 = 98%)
→ 운임단가 테이블에서 예상운임 계산 (예: CBM 2.5 × 수도권 단가)

STEP 2. 출하 실행 (Shipment 생성)
Shipment 생성 시:
- 약속납기일 입력 (고객 약속일)
- 약속수량 입력
→ 발송상태_TMS = "출하완료" 설정
→ [자동] OTIF 레코드 생성
→ [수동] 배송이벤트 "픽업완료" 기록

STEP 3. 배송 중
이동 단계마다 배송이벤트 레코드 추가:
- 이벤트유형: 픽업완료 → 허브도착 → 배송중
- 택배의 경우 택배추적로그에도 기록 (API 연동 또는 수동)

STEP 4. 배송 완료
배송 완료 확인:
→ 배송이벤트 "배송완료" 기록
→ Shipment.POD_확인일시 / POD_수령자명 입력
→ OTIF 실제배송일 / 실제수량 입력
→ On_Time / In_Full / OTIF_Score 자동 계산

STEP 5. 이상 발생 시
파손/분실/오배송:
→ 배송클레임 레코드 생성
→ Shipment / 배송파트너 링크
→ 처리 완료 후 재발방지대책 기록

STEP 6. 월 마감
→ 정산관리: 해당 월 Shipment 전체 링크
→ 비용 집계 입력 → 물류손익 자동 계산
→ 세금계산서 발행 후 번호 입력
→ 배송파트너.월간_OTIF달성률 확인 → 성과 평가
```

---

## 필드 입력 가이드 (운용 시 주의사항)

| 테이블 | 필수 입력 필드 | 자동 계산 필드 | 나중에 채워도 되는 필드 |
|--------|--------------|--------------|----------------------|
| OTIF | 실제배송일, 실제수량 | On_Time, In_Full, OTIF_Score, 납기차이일 | 미달성사유, 비고 |
| 배송이벤트 | 이벤트유형, 이벤트일시, Shipment | - | 위치, 증빙사진 |
| 운임단가 | 단가코드, 배송파트너, 구간유형, CBM구간, 기본운임 | - | CBM당_추가운임, 유효종료일 |
| 배송SLA | SLA코드, 구간유형, 배송방식, OTIF목표 | - | 패널티조건, 목표배송시간 |
| 배송클레임 | 클레임번호, 클레임유형, 발생일, Shipment | - | 보상금액, 완료일 |
| 정산관리 | 정산번호, 정산월, 운송비, Shipment | 총물류비, 물류손익 | 세금계산서번호 |
| 택배추적로그 | 택배사, 운송장번호, 추적상태, 추적일시, Shipment | - | 추적위치, 수령인 |

---

## 주요 FAQ

**Q. OTIF_Score가 FALSE가 되려면?**
- On_Time = FALSE: 실제배송일 > 약속납기일 (납기 초과)
- In_Full = FALSE: 실제수량 < 약속수량 (수량 부족)
- 둘 중 하나라도 FALSE면 OTIF_Score = FALSE

**Q. 배송이벤트와 발송상태_TMS의 차이?**
- 발송상태_TMS (Shipment 필드): 현재 상태 단 1개 (최신값만 표시)
- 배송이벤트: 전체 이력 (변화 과정 모두 기록)

**Q. 택배추적로그는 언제 만드나?**
- 로젠택배 등 운송장번호 있는 건: 추적 조회 후 기록
- 기사 직배송: 택배추적로그 불필요 (배송이벤트만 기록)

**Q. 정산관리에 Shipment를 어떻게 연결하나?**
- 정산관리 레코드의 Shipment 필드에서 해당 월 Shipment 검색하여 다중 선택
- 현재 3월: 349건 연결 필요 (200건만 됨)

---

## 다음 작업 (WMS Phase)

TMS 완료 후 WMS Phase 착수 우선순위:
1. **W-NEW-01**: ⚡movement 테이블에 `SAP_이동유형` singleSelect 필드 추가
2. **W-NEW-06**: ⚡material 테이블에 자재상태/안전재고/ABC등급 필드 추가
3. **W-1**: 불량코드 마스터 테이블 신규 생성 + 시드 21건 입력
