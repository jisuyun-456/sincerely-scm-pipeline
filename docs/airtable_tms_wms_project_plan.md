# Airtable SAP 보완 프로젝트 — 운영 플랜

> 최종 갱신: 2026-04-02  
> 기준: SAP S/4HANA TM/EWM/QM 글로벌 표준 vs 신시어리 Airtable AS-IS  
> 이 문서는 새 채팅에서 이어받아 WMS Phase를 착수하기 위한 핸드오프 문서입니다.

---

## 프로젝트 배경 (Q1 2026 근거)

| 지표 | 목표 | 실적 | 상태 |
|------|------|------|------|
| QC 불량률 | ≤1.0% | **20.6%** (2월 40.76% spike) | CRITICAL |
| 차량 이용률 | ≥80% | **27~57%** | HIGH |
| 미입하 건수 | 0 | **107건** 미해결 | HIGH |
| 음수재고 | 0 | **331건** | CRITICAL |
| OTIF | ≥95% | **측정 시작** (Q2부터 데이터 축적) | 진행 중 |

---

## TMS Phase 1 — 완료 현황

### 베이스 정보
- **TMS 베이스 ID:** `app4x70a8mOrIKsMf`
- 기존 10개 테이블 → 현재 **17개** 테이블

---

### 완료된 테이블 목록 (Airtable ID 포함)

| 테이블명 | 테이블 ID | 상태 | 비고 |
|---------|----------|------|------|
| Shipment | `tbllg1JoHclGYer7m` | 기존 + 필드 추가 | 약속납기일, POD 등 추가 |
| 배송파트너 | `tblI4ZXrte7WyhXyd` | 기존 + 필드 추가 | 클레임건수, 파손건수 추가 |
| 배차 일지 | `tbl0YCjOC7rYtyXHV` | 기존 + 필드 추가 + 데이터 생성 | 3월~4월3일 102건 생성 |
| **OTIF** | `tbl4WfEuGLDlqCTQH` | ✅ 신규 생성 + 백필 완료 | 348건 |
| **배송이벤트** | `tblQyuAW30yf21WEf` | ✅ 신규 생성 + 백필 완료 | 349건 |
| **운임단가** | `tblQA1ev9fjbowUoP` | ✅ 신규 생성 + 마스터 완료 | 15건 |
| **배송SLA** | `tblbPC6z0AsbvcVxJ` | ✅ 신규 생성 + 마스터 완료 | 9건 |
| **배송클레임** | `tblIZ9kco1QDpUz0u` | ✅ 신규 생성 | 0건 (실제 발생 시 수동 입력) |
| **정산관리** | `tblf0BClxZtnQfOJL` | ✅ 신규 생성 + 집계 완료 | 2건 (3월/4월) |
| **택배추적로그** | `tblonyqcHGa5V5zbj` | ✅ 신규 생성 + 백필 완료 | 73건 (로젠택배 운송장) |

---

### Shipment 필드 추가 내역

| 필드명 | 필드 ID | 타입 | 설명 |
|--------|---------|------|------|
| 약속납기일 | `fldyYIfBhhu7sEX1P` | date | OTIF 측정 기준일 |
| 약속수량 | `fldJ5czWvSJ1NMQmW` | number | OTIF 기준 수량 |
| POD_확인일시 | `fldNPH5xLdYevknfZ` | dateTime | 수령 확인 시점 |
| POD_수령자명 | `fld6OTjF9Tw6GdwJb` | singleLineText | 수령인 |
| POD_불일치여부 | `fldtNZnDMf10cbxkQ` | checkbox | 수량/품목 불일치 |
| 배차일지_매칭키 | `fldoQV2ksYHLuLZvE` | formula | 배차 자동화 매칭용 (`출하확정일_배송파트너명`) |
| OTIF | `fldQEpW6QI8Qg3nDn` | multipleRecordLinks | OTIF 테이블 연결 |
| 배송이벤트 | `fldtS7VtbyXaAKTl7` | multipleRecordLinks | 배송이벤트 연결 |
| 배송클레임 | `fldS2mABpzmtudiPc` | multipleRecordLinks | 배송클레임 연결 |
| 정산관리 | `fldgl8LtobJeZThxI` | multipleRecordLinks | 정산관리 연결 |
| 택배추적로그 | `fldHGqWyi0aqwNve7` | multipleRecordLinks | 택배추적로그 연결 |

---

### 배차 일지 현황

| 항목 | 내용 |
|------|------|
| 생성 기간 | 2026-03-01 ~ 2026-04-03 (34일) |
| 기사 | 박종성 (`recXCfwVTqaoeQ9SS`), 이장훈 (`recyVExCkk2Lty0E9`), 조희선 (`recPkgE4o3cs0krnR`) |
| 생성 레코드 수 | 102건 (34일 × 3명) |
| Shipment 연결 | 3월~4월2일 실제 Shipment 데이터 연결 완료 |
| 오버부킹 발견 | 3건 (3/13 조희선 107.7%, 3/16 이장훈 141%, 4/3 박종성 191%) |
| 주요 필드 ID | 날짜:`fldZh2mZDIPQXfOcO`, 배정물량_합계:`flddCIndicSSe8uhi`, 차량이용률:`fldyQAoRZFn6oeQ0E` |

---

### 백필 완료 데이터 요약

| 테이블 | 건수 | 기간 | 데이터 품질 메모 |
|--------|------|------|----------------|
| OTIF | 348건 | 3월~4월2일 | 약속납기일 = 출하확정일 (proxy). On_Time 모두 달성으로 표시됨. 향후 실제 약속납기일 입력 시 재계산. |
| 배송이벤트 | 349건 | 3월~4월2일 | 이벤트유형=배송완료, 이벤트일시=출하확정일 09:00. 중간 이벤트 없음. |
| 택배추적로그 | 73건 | 3월~4월2일 | 숫자형 운송장(8~15자리)만 필터. 로젠택배 전량. 추적상태=배송완료. |
| 운임단가 | 15건 | - | Q1 운송비 역산 기준. 기사 3명×4구간 + 로젠/고고엑스/베스트원. |
| 배송SLA | 9건 | - | 구간유형 4개 × 배송방식 3개. OTIF목표 70~98%. |
| 정산관리 | 2건 | 3월/4월 | 3월=8,553,350원(200건 기준), 4월=0(미정산). 전체 349건 재집계 필요. |

---

### Automation 현황

| 오토메이션 | 트리거 | 액션 | 상태 |
|-----------|--------|------|------|
| OTIF 자동생성 | Shipment.발송상태_TMS = "출하완료" | OTIF 레코드 신규 생성 | ✅ 운영 중 |
| 배차일지 자동연결 | Shipment.출하확정일 not empty AND 배송파트너 not empty | 배차일지_매칭키 기준 배차일지 탐색 → Shipment.배차일지 연결 | ✅ 운영 중 |

---

### 미완료 TMS 항목

| 항목 | 이유 | 해결방법 |
|------|------|---------|
| 배송클레임 데이터 | 실제 클레임 발생 기록 없음 | 실제 발생 시 수동 입력 |
| 정산관리 3월 최종금액 | 200건 기준 집계 (349건 미반영) | 추후 전체 운송비 합계로 업데이트 |
| 운임단가 지방/도서산간 | 기사 직배송은 수도권 전용 | 해당 노선 발생 시 추가 |
| ASN_입하예정 | WMS 도메인으로 이관됨 | WMS Phase에서 처리 |

---

## WMS Phase 2 — 실행 계획

### 베이스 정보
- **WMS 베이스 ID:** `appLui4ZR5HWcQRri`

### 현재 WMS 테이블 현황 (14개)

| 테이블명 | 역할 | 비고 |
|---------|------|------|
| ⚡movement | 입출고 원장 (495필드) | 핵심 테이블 |
| ⚡material(parts-stock) | 재고 현황 | 안전재고 필드 없음 |
| ⚡sync_parts | 자재 마스터 | |
| ⚡sync_partner | 공급사 마스터 | |
| ⚡logistics_release | 출고지시 | |
| ⚡purchasing | 구매발주 | |
| ⚡real_stock | 실사재고 | 미운영 |
| ⚡실사문서 | 실사 계획 | 미운영 |
| ⚡실사카운트 | 실사 수행 | 미운영 |
| ⚡실사결과_클로징 | 실사 확정 | 미운영 |
| 기타 4개 | 보조 테이블 | |

---

### PHASE 0: 기반 정비 (1주차, 즉시 착수)

> 모든 WMS 작업의 전제조건. 병렬 착수 가능.

#### W-NEW-01: movement에 SAP_이동유형 필드 추가

- **대상:** ⚡movement 테이블
- **작업:** `SAP_이동유형` singleSelect 필드 추가
- **이유:** 현재 `이동유형` 필드는 multilineText → 필터/집계 불가 → 음수재고 331건 원인

**singleSelect 선택지:**

| 선택지 | SAP 코드 | 재고 영향 |
|--------|---------|----------|
| 101_구매입고 | 101 | + |
| 102_입고취소 | 102 | - |
| 122_공급사반품 | 122 | - |
| 161_고객반품입고 | 161 | + |
| 201_원가센터출고 | 201 | - |
| 261_생산투입 | 261 | - |
| 262_생산반납 | 262 | + |
| 301_재고이전 | 301 | ±이전 |
| 501_PO없는입고 | 501 | + |
| 551_폐기출고 | 551 | - |
| 601_납품출고 | 601 | - |
| 701_재고조정+ | 701 | + |
| 702_재고조정- | 702 | - |

**MCP 작업:** `create_field` → movement 테이블에 singleSelect 필드 추가

---

#### W-NEW-06: material에 자재상태/안전재고 필드 추가

- **대상:** ⚡material(parts-stock) 테이블
- **이유:** 자재상태 없으면 불량 자재 격리 불가, 안전재고 없으면 ROP 알림 불가

**추가 필드:**

| 필드명 | 타입 | 설명 |
|--------|------|------|
| 자재상태 | singleSelect | 자유재고 / 품질검사중 / 차단 / 반품 |
| 안전재고수량 | number | ROP 트리거 기준값 |
| ABC등급 | singleSelect | A(고가치/월1회 실사) / B / C |
| 상태변경일 | date | 마지막 상태 변경일 |
| 상태변경사유 | singleLineText | |

**MCP 작업:** `create_field` → material 테이블에 5개 필드 추가

---

### PHASE 1: 품질/재고 정확성 (2주차)

> Q1 불량률 20.6%와 음수재고 331건 직접 해결

#### W-1: 불량코드 마스터 테이블 생성 (신규)

- **SAP 대응:** QS41 Defect Catalog
- **MCP 작업:** `create_table` → WMS 베이스에 신규 생성

**필드:**

| 필드명 | 타입 |
|--------|------|
| 불량코드 | singleLineText (PK) |
| 불량명 | singleLineText |
| 카테고리 | singleSelect: 인쇄/제조/자재/치수/포장/라벨/오염 |
| 심각도 | singleSelect: Critical/Major/Minor |
| 적용자재그룹 | singleSelect: 스티커/파우치/박스/다이어리/전체 |
| 설명 | multilineText |
| 활성여부 | checkbox |

**시드 데이터 21건 (create_records_for_table):**

| 코드 | 불량명 | 카테고리 | 심각도 |
|------|--------|---------|--------|
| PRT-001 | 인쇄 색상 불일치 | 인쇄 | Major |
| PRT-002 | 인쇄 번짐 | 인쇄 | Major |
| PRT-003 | 오탈자 | 인쇄 | Critical |
| PRT-004 | 인쇄 누락 | 인쇄 | Critical |
| PRT-005 | 인쇄 위치 오차 | 인쇄 | Minor |
| PRT-006 | 잉크 번짐 | 인쇄 | Minor |
| MFG-001 | 재봉 불량 | 제조 | Major |
| MFG-002 | 본딩 불량 | 제조 | Major |
| MFG-003 | 가죽 스크래치 | 제조 | Major |
| MFG-004 | 금속부품 불량 | 제조 | Critical |
| MAT-001 | 자재 변색 | 자재 | Minor |
| MAT-002 | 자재 강도 불량 | 자재 | Major |
| MAT-003 | 이물질 혼입 | 자재 | Critical |
| PKG-001 | 포장 파손 | 포장 | Minor |
| PKG-002 | 포장 오염 | 포장 | Minor |
| PKG-003 | 포장 누락 | 포장 | Major |
| PKG-004 | 실링 불량 | 포장 | Major |
| CON-001 | 곰팡이/오염 | 오염 | Critical |
| CON-002 | 악취 | 오염 | Major |
| DIM-001 | 치수 불일치 | 치수 | Major |
| DIM-002 | 중량 불일치 | 치수 | Minor |

---

#### W-2: 이슈관리(NCR) 테이블 생성 (신규)

- **SAP 대응:** QM01 Quality Notification
- **MCP 작업:** `create_table` → WMS 베이스, 이후 movement 링크 필드 추가
- **선행:** W-1 불량코드 생성 완료 후

**필드:**

| 필드명 | 타입 |
|--------|------|
| 이슈번호 | formula (NCR-YYYYMMDD-NNN) |
| movement | multipleRecordLinks → movement |
| 이슈유형 | singleSelect: 품질이슈/수량이슈/운영이슈/미입하/납기지연 |
| 불량코드 | multipleRecordLinks → 불량코드 |
| 발견수량 | number |
| 심각도 | singleSelect: Critical/Major/Minor |
| 이슈상세 | multilineText |
| 증빙사진 | multipleAttachments |
| 발생원인 | singleSelect: 공급사QC미흡/디자인오류/운송파손/작업자실수/자재불량 |
| 대응방안 | multipleSelects: 반품/재제작/수량보충/가격협의/폐기/사용승인 |
| 처리상태 | singleSelect: 접수/조사중/대응중/완료/종결 |
| 담당자 | singleCollaborator |
| 접수일 | createdTime |
| 완료일 | date |
| 재발방지대책 | multilineText |

---

#### W-3: 검사기준 마스터 테이블 생성 (신규)

- **SAP 대응:** QP01 Inspection Plan + ISO 2859 AQL
- **MCP 작업:** `create_table` → WMS 베이스
- **선행:** W-1 불량코드 생성 완료 후

**필드:**

| 필드명 | 타입 |
|--------|------|
| 자재 | multipleRecordLinks → sync_parts |
| 검사유형 | singleSelect: 입하검수/공정검수/최종검수 |
| AQL_레벨 | singleSelect: Level I(완화)/Level II(보통)/Level III(강화) |
| 필수검사항목 | multipleSelects: 수량확인/시안대조/치수측정/색상확인/인쇄품질/포장상태 |
| 합격기준 | multilineText |
| 불합격시_조치 | singleSelect: 전수검수/반품/폐기/사용승인_요청 |
| 유효시작일 | date |
| 비고 | multilineText |

---

#### W-NEW-02: material에 LOT/배치 격리 필드 추가

- **대상:** ⚡material(parts-stock) 테이블
- **선행:** W-1 불량코드, W-NEW-01 이동유형
- **MCP 작업:** `create_field` × 6개

**추가 필드:**

| 필드명 | 타입 |
|--------|------|
| LOT번호 | singleLineText |
| LOT상태 | singleSelect: 자유재고/품질검사중/차단/반품대기 |
| 격리사유 | singleSelect: 불량판정/유통기한임박/고객클레임/공급사리콜/조사중 |
| 격리일 | date |
| 격리해제일 | date |
| 격리판정자 | singleCollaborator |

---

#### W-NEW-05: 실사 3개 테이블 활성화 + 필드 추가

- **대상:** ⚡실사문서, ⚡실사카운트, ⚡실사결과_클로징 (현재 미운영)
- **선행:** W-NEW-01 이동유형 (701/702 코드 필요)
- **MCP 작업:** `create_field` → 각 테이블에 필드 추가

**실사문서 추가 필드:**

| 필드명 | 타입 |
|--------|------|
| ABC분류 | singleSelect: A(월1회)/B(분기1회)/C(반기1회) |
| 실사방법 | singleSelect: 전수실사/순환실사/스팟실사 |
| 트리거사유 | singleSelect: 정기실사/음수재고발견/고객클레임/입출고차이/기타 |

**실사카운트 추가 필드:**

| 필드명 | 타입 |
|--------|------|
| LOT번호 | singleLineText |
| 좌표확인 | singleLineText |
| 실사사진 | multipleAttachments |

**실사결과_클로징 추가 필드:**

| 필드명 | 타입 |
|--------|------|
| movement_link | multipleRecordLinks → movement |
| 원인분석 | singleSelect: 전산오류/도난/파손미신고/중복입고/출고미기장/기타 |
| 시정조치 | multilineText |

---

### PHASE 2: 운영 효율화 (3주차)

#### W-4: 공급사 단가이력 테이블 생성 (신규)

- **SAP 대응:** ME11 Purchasing Info Record
- **MCP 작업:** `create_table` → WMS 베이스

**필드:**

| 필드명 | 타입 |
|--------|------|
| 자재 | multipleRecordLinks → sync_parts |
| 공급사 | multipleRecordLinks → sync_partner |
| 단가 | currency |
| MOQ | number |
| 리드타임(일) | number |
| 결제조건 | singleSelect: 선결제/net30/net60 |
| 유효시작일 | date |
| 유효종료일 | date |
| 최근발주일 | date |
| 최근발주단가 | currency |
| 우선공급사 | checkbox |
| 비고 | multilineText |

---

#### W-5: movement 뷰 6개 생성 (기존 테이블)

- **대상:** ⚡movement 테이블
- **MCP 작업:** Airtable UI에서 직접 뷰 생성 (MCP는 뷰 생성 미지원)

| 뷰 이름 | 필터 조건 | 목적 |
|---------|----------|------|
| 📥 입하대기 | 이동목적=입고 AND 입하여부=미입하 | 미입하 107건 추적 |
| 🔍 검수진행 | 입하여부=입하완료 AND 수량검수결과=empty | AQL 검수 진행 중 |
| 📦 입고확정 | 수량검수결과≠empty AND 입고수량=empty | 입고 확정 대기 |
| 🚚 출고진행 | 이동목적=출고 AND 출고상태≠완료 | 출고 현황 |
| ⚠️ 이슈현황 | 품질이슈=TRUE OR 운영이슈=TRUE OR 수량이슈=TRUE | 이슈 집중 관리 |
| 📊 음수재고 | (필터: SAP_이동유형 이용해서 재고 음수 계산) | 331건 해소 추적 |

---

#### W-6: ROP 자동 알림 Automation

- **대상:** material 테이블 → Slack 알림
- **선행:** W-NEW-06 (안전재고수량 필드) 추가 완료 후
- **MCP 작업:** Airtable UI에서 Automation 설정

**설정:**
- Trigger: material 레코드 업데이트 시 `가용재고수량 <= 안전재고수량` AND `안전재고수량 > 0`
- Action: Slack #scm-alerts 채널 메시지
- 메시지: `⚠️ [자재명] 재고 부족: 가용재고 {가용재고수량} / 안전재고 {안전재고수량}`

---

#### W-ASN: movement 테이블에 입하대기 뷰 추가

- TMS에서 잘못 생성했던 `ASN_입하예정` 테이블은 UI에서 삭제 완료
- movement 테이블에 `📥 입하대기` 뷰 추가 (W-5와 함께 처리)
- 필요 시 movement에 추가 필드: `예정입하일` (date), `운송수단` (singleSelect), `운송장번호_ASN` (singleLineText)

---

### PHASE 3: 고도화 (4주차)

#### W-NEW-03: 피킹리스트 테이블 생성 (신규)

- **SAP 대응:** /SCWM/TO Warehouse Task
- **선행:** W-NEW-01 이동유형
- **MCP 작업:** `create_table`

**필드:**

| 필드명 | 타입 |
|--------|------|
| 피킹번호 | singleLineText (PICK-YYYYMMDD-NNN) |
| 출고지시 | multipleRecordLinks → logistics_release |
| 피킹자재 | singleLineText |
| 피킹수량 | number |
| 확정수량 | number |
| 피킹좌표 | singleLineText |
| 피킹상태 | singleSelect: 지시/진행중/완료/부족/취소 |
| 피킹담당자 | singleCollaborator |
| 피킹시작시간 | dateTime |
| 피킹완료시간 | dateTime |
| 부족사유 | singleSelect: 재고부족/위치오류/파손발견/기타 |
| 비고 | multilineText |

---

### WMS 구조적 이슈 (의사결정 필요)

**S-01: movement 이중화 해소**
- 문제: WMS.movement(495필드)와 자재관리.movement(445필드) 동시 존재
- 원인: 같은 재고이동이 두 곳에 다르게 기록 → 음수재고 331건 구조적 원인
- 해결: **WMS.movement를 SSOT(Single Source of Truth)로 선정**, 자재관리.movement는 Read-only 전환
- **착수 전 팀 합의 필요**

---

## 전체 실행 순서 요약

```
PHASE 0 (즉시, 병렬)
  W-NEW-01: movement SAP_이동유형 필드 추가
  W-NEW-06: material 자재상태/안전재고/ABC 필드 추가

PHASE 1 (2주차)
  W-1: 불량코드 마스터 테이블 생성 + 시드 21건 입력
  W-2: 이슈관리(NCR) 테이블 생성
  W-3: 검사기준 마스터 테이블 생성
  W-NEW-02: material LOT 격리 필드 추가
  W-NEW-05: 실사 3개 테이블 필드 추가 + 활성화

PHASE 2 (3주차)
  W-4: 공급사 단가이력 테이블 생성
  W-5 + W-ASN: movement 뷰 6개 생성 (UI 작업)
  W-6: ROP 자동 알림 Automation (UI 작업)

PHASE 3 (4주차)
  W-NEW-03: 피킹리스트 테이블 생성
  KPI Dashboard: Airtable Interface 구축
```

---

## 성공 지표 (Q2 목표)

| 지표 | Q1 실적 | Q2 목표 | 해결 과제 |
|------|---------|---------|---------|
| QC 불량률 | 20.6% | **≤5%** | W-1, W-2, W-3, W-NEW-02 |
| 음수재고 | 331건 | **0건** | W-NEW-01, W-NEW-05, S-01 |
| OTIF 달성률 | 측정 시작 | **≥90%** | 데이터 축적 중 (3월~4월 348건 기록) |
| 미입하 | 107건 | **≤10건** | W-ASN (입하대기 뷰) |
| 차량 이용률 | 27~57% | **≥70%** | 배차일지 오버부킹 감지 운영 중 |
| 자재 단가 미입력 | 8건 | **0건** | W-4 공급사 단가이력 |

---

## 다음 채팅에서 이어받기 가이드

**착수 우선순위:**
1. `W-NEW-01` — movement 테이블에 `SAP_이동유형` singleSelect 필드 추가 (가장 먼저)
2. `W-NEW-06` — material 테이블에 5개 필드 추가 (병렬 가능)
3. `W-1` — 불량코드 마스터 테이블 생성 + 시드 21건 입력

**MCP 도구:**
- `mcp__claude_ai_Airtable__list_tables_for_base(appLui4ZR5HWcQRri)` — WMS 현황 확인
- `mcp__claude_ai_Airtable__create_field` — 기존 테이블 필드 추가
- `mcp__claude_ai_Airtable__create_table` — 신규 테이블 생성
- `mcp__claude_ai_Airtable__create_records_for_table` — 시드 데이터 입력

**참고 플랜 파일:** `C:\Users\yjisu\.claude\plans\jolly-kindling-blum.md`
