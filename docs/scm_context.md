# Sincerely SCM — Claude Code 컨텍스트 문서
> claude.ai 대화 인계용. VS Code에서 이 파일을 @참조하면 이전 작업을 이어서 진행할 수 있습니다.

---

## 1. 프로젝트 개요

**회사:** 신시어리 (Sincerely) — 한국 프로모션 굿즈 회사  
**담당자:** 지수 (SCM/물류팀, 포장 재고 관리 / 입출고 / 배송)  
**주요 도구:** Airtable (ERP — WMS + TMS), GitHub Actions, Python, Supabase  
**GitHub 레포:** `jisuyun-456/sincerely-scm-pipeline`  
**VS Code 프로젝트:** `sincerely-scm` (`.claude/commands/` 슬래시 커맨드, `skills/` 폴더 구성됨)

---

## 2. Airtable 구조

### TMS Base
- **Base ID:** `app4x70a8mOrIKsMf`

| 테이블 | Table ID |
|--------|----------|
| Shipment (출하) | `tbllg1JoHclGYer7m` |
| Box | `tbltwH7bHk41rTzhM` |
| Product | `tblBNh6oGDlTKGrdQ` |
| 배송요청 | `tblfIEiPJaHclGYer7m` |

### Shipment 테이블 핵심 Field ID

| 필드명 | Field ID |
|--------|----------|
| 출하확정일 | `fldQvmEwwzvQW95h9` |
| 최종 출하 품목 | `fldgSupj5XLjJXYQo` |
| 최종 외박스 수량 값 (formula) | `fldTjLDmw5sNGszeD` |
| 외박스 수량 직접입력 | `fldRjMaXa5TdSsGDL` |
| Total_CBM (수동입력) | `fldJ9DHjwoRyeUEqE` |
| 발송상태_TMS | `fldOhibgxg6LIpRTi` |
| 물류매출 | `fldOFuvqBT0iXItcT` |
| 운송비용 | `fldRT95SC88KSBATT` |
| 배송파트너 | `fldHZ7yMT3KEu2gSj` |

### Product 테이블 핵심 Field ID

| 필드명 | Field ID |
|--------|----------|
| 품목명 (Name) | `fldx01uKEnCd0J0nP` |
| 박스규격 (select) | `fldGpEXIndaI70PQn` |
| 박스당 제품 수량 | `fldENIdfxbVn8YnPI` |
| 박스당 CBM (단품, 수식) | `fldCeJ0RqSUGlfEw4` |
| 박스당 CBM (단품, fldN) | `fldN1JrkxIr5m6pXz` |
| 박스당 CBM (키트) | `fld6W5ImO7UeBVMPI` |
| 박스사이즈 (극소~특대) | `fldqGM1lw2TUpZdKW` |
| 품목코드 (SKU) | `fldtpUf2UVooLcxwd` |

### 박스 규격 CBM 기준값

| 규격 | 코드 | CBM/박스 |
|------|------|----------|
| 극소형 | S280 | 0.0098 |
| 소형 | S360 | 0.0117 |
| 중형 | M350 | 0.0201 |
| 중대형 | M480 | 0.0492 |
| 대형 | L510 | 0.1066 |
| 특대형 | L560 | 0.1663 |

---

## 3. GitHub Actions 파이프라인

### 파일 구조 (레포 루트)
```
sincerely-scm-pipeline/
├── sincerely_weekly_report_v2.py    # 주간 출하 리포트
├── sincerely_monthly_report.py      # 월간 출하 리포트
├── .github/workflows/
│   ├── weekly_scm_report_v2.yml
│   └── monthly_scm_report.yml
└── sincerely_scm_context.md         # 이 파일
```

### GitHub Secrets

| Secret 이름 | 용도 |
|------------|------|
| `AIRTABLE_API_KEY` | 주간 리포트용 Airtable PAT |
| `AIRTABLE_BASE_ID` | `app4x70a8mOrIKsMf` |
| `AIRTABLE_API_KEY_TMS` | 월간 리포트용 Airtable PAT |
| `AIRTABLE_BASE_TMS_ID` | `app4x70a8mOrIKsMf` |
| `SLACK_BOT_TOKEN` | `xoxb-...` |
| `SLACK_DM_USER_ID` | Slack User ID (U로 시작) |

---

## 4. CBM 산출 로직 (v3 현행)

### 우선순위
```
1순위: Total_CBM 수동 입력 (fldJ9DHjwoRyeUEqE)
2순위: Product 테이블 품목명 매칭 (공백 제거 후 부분일치, greedy)
3순위: 외박스 수량 문자열 파싱 (극소N, 중대N 패턴)
4순위: 모두 없으면 CBM = 0.0 (집계 제외)
```

### 핵심 함수 요약

```python
def fetch_product_cbm():
    # Product 테이블 전체 조회, field ID로 직접 접근
    # fields= 파라미터 쓰면 0개 나옴 — 반드시 table.all() 후 f.get("fldxxx") 방식으로
    # 반환: [(normalized_name, cbm_per_box), ...] 긴 이름 순 정렬

def match_cbm_from_product(item_str, product_cbm):
    # 공백 제거 후 부분일치 (greedy: 긴 이름 우선)
    # 줄별로 파싱, 끝 숫자를 수량으로 인식해 cbm_per_box * qty 계산
    # 매칭 안 되면 0.0 반환

def parse_box_cbm(box_str, live):
    # "중대3 / 총3박스" 패턴 파싱
    # _BOX_RE = r"(극소|소|중대|중|대|특대|S280|...)\s*(\d+)"

def analyze(records, live_cbm, week_start, product_cbm=None):
    # cbm_sources = {"manual": 0, "box_parse": 0, "product_match": 0, "unmatched": 0}
    # 반환: summary / by_date / box_type / quality / cbm_sources / top_items

def build_trend(prev_records, live_cbm, product_cbm=None):
    # 최근 4주 주간 CBM + 손익 트렌드
```

### 주요 트러블슈팅 이력

| 문제 | 원인 | 해결 |
|------|------|------|
| `SyntaxError: invalid character '"'` | 모바일 편집시 스마트쿼트 삽입 | 바이트 단위 치환 후 저장 |
| `Product CBM 조회 완료: 0개` | `table.all(fields=[...])` 에 field ID 넣으면 pyairtable이 이름으로 처리 | `fields=` 제거, `table.all()` 후 `f.get("fldxxx")` |
| `KeyError: 'estimate'` | 슬랙 빌더에 구버전 키 잔존 | `estimate` → `product_match`, `none` → `unmatched` |

---

## 5. 매칭률 분석 결과 (24.01 ~ 26.02, 8000건)

| 구분 | 건수 | 비율 |
|------|------|------|
| 품목 기재 건 중 매칭 성공 | 4,650건 | 83.4% |
| 품목 기재 건 중 매칭 실패 | 927건 | 16.6% |
| 품목 미기재 | 2,423건 | 30.3% |

**매칭 실패 주요 패턴:**
- 변형 표기: `Passion더스트백(블랙M)키트` — 색상/사이즈 추가 텍스트
- 주문코드 포함: `PT2472-트리플컬러펜_블랙 || 1500개`
- Product 테이블 미등록: `스티커`, `웰컴페이퍼`, `노트류지지대`
- 규격 미특정: `밸류메모큐브 300` (S/M 구분 없음)

**현재 방향:** 지금은 83% 매칭으로 운영, 향후 Product 테이블 데이터 정합성 통일 후 재매칭 예정.

---

## 6. SCM 대시보드 (진행 중)

### 개념
- **형태:** Claude AI 기반 인터랙티브 아티팩트 (Claude.ai 위젯)
- **구성:** 입고 / 검수 / 자재 / 출하 4개 탭
- **기간 선택:** 월간(월 칩) / 주간(주차 칩) 전환
- **데이터:** Airtable 실시간 연동 (출하 탭 구현 완료)
- **팀 공유:** Claude.ai 대화 링크 공유 또는 향후 GitHub Pages 배포

### 출하 탭 현황 (구현 완료)
- 일별/주차별 CBM + 건수 차트 (Chart.js)
- 배송파트너별 건수 바 차트
- 주요 출하 품목 Top (CBM 기준)
- CBM 산출 근거 (수동/품목매칭/박스파싱/미산출)
- 미완료 건수 알림, CBM 미산출 경고

### 입고/검수/자재 탭
- 현재 "준비 중" 상태
- Airtable 테이블 구조 공유받으면 동일 방식으로 연결 예정

---

## 7. PENDING 작업 목록

- [ ] **대시보드 — 입고/검수/자재 탭 연결** (Airtable 구조 확정 후)
- [ ] **대시보드 — GitHub Pages 배포** (팀 공유용 고정 URL)
- [ ] **월간 리포트 — GitHub Actions 테스트 실행** (`SKIP_DELAY=1` 환경변수로)
- [ ] **주간 리포트 — Product 테이블 매칭률 개선** (CBM 데이터 정합성 통일 후)
- [ ] **Supabase 재고 스냅샷 파이프라인** (`sincerely-scm-pipeline` 레포 내)
  - 실사 3-table 구조: 실사문서 1:N 실사카운트 1:1 실사결과_클로징
  - SAP-style physical inventory 구조 설계 완료, Supabase 연동 테스트 진행됨

---

## 8. 기술 스택 & 환경

```
Python 3.11 (GitHub Actions: hostedtoolcache)
pyairtable — Airtable API 클라이언트
requests — Slack API 호출
Supabase (PostgreSQL) — 재고 스냅샷 저장
GitHub Actions — 자동화 스케줄러
VS Code + Claude Code — 개발 환경
```

### 주의사항
- Python 파일에 이모지/특수문자(스마트쿼트, em dash, 박스라인 등) 절대 금지
- 모바일로 GitHub 편집 시 자동 스마트쿼트 삽입됨 → 반드시 데스크탑에서 편집
- pyairtable `table.all(fields=[field_id])` — field ID로 필터 안 됨, 전체 조회 후 `f.get("fldxxx")`

---

## 9. 다음 Claude Code 세션에서 바로 시작하려면

```
@sincerely_scm_context.md 참고해서 작업 이어서 진행해줘.

우선순위:
1. 대시보드 입고/검수/자재 탭 Airtable 연결
2. 월간 리포트 Actions 테스트
3. GitHub Pages 배포 구성
```
