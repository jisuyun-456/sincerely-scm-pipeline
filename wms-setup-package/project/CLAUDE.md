# Sincerely WMS

신시어리 포장재 물류팀 WMS 시스템. Airtable 운영 데이터를 기반으로 한 창고 관리 시스템.

## 이 프로젝트 열면 자동 실행
다른 것보다 먼저, 아래를 즉시 실행할 것:
1. `git log --oneline -10` → 최근 작업 히스토리 확인
2. `_AutoResearch/WMS/wiki/log.md` → 마지막 AutoResearch 상태 확인 (Obsidian MCP 또는 직접 읽기)
실행 후 "현재 상태 요약 + 다음 추천 태스크 1개"를 나에게 말해줄 것.
세션 종료 시: git commit 필수.

## Graphify Knowledge Graph
코드베이스 knowledge graph (Karpathy Wiki 패턴, `pip install graphifyy`):
- 그래프 위치: `graphify-out/graph.json`
- 코드 구조 탐색: `/graphify query "질문"` 또는 `/graphify path A B`
- 커밋 시 자동 rebuild (git post-commit hook 설치됨)
- 수동 업데이트: `graphify update .` (또는 `python -m graphify update .`)

## 데이터 정합성 원칙
- Airtable: 운영 입력 레이어 — API로만 읽기, 직접 수정 금지
- Supabase: 불변 원장 — InventoryTransaction INSERT ONLY, 수정/삭제 금지
- 재고 정정 = Storno(역분개) 후 재기표. UPDATE/DELETE 절대 금지

## 회계/ERP 기준
- K-IFRS 기준 / 더존 아마란스10 계정코드 체계 (1xxx자산~5xxx비용)
- SAP 이동유형: 101입고 / 122공급사반품 / 201출고 / 261생산출고 / 311이전 / 601납품 / 701조정+ / 702조정-

## 기술 스택
| 레이어 | 도구 | 상태 |
|--------|------|------|
| 운영 입력 | Airtable (WMS base) | 운영 중 |
| 불변 원장 | Supabase PostgreSQL (wms 스키마) | 운영 중 |
| 백엔드 | NestJS | 운영 중 |
| 파이프라인 | GitHub Actions + Python | 운영 중 |
| 코드 그래프 | Graphify (graphify-out/) | 운영 중 |
| 지식 검색 | LightRAG + Obsidian | 운영 중 |

## WMS 도메인 규칙

### Stock Type (재고 유형)
- `UNRESTRICTED`: 출고 가능한 실재고
- `QUALITY_INSPECTION`: QC 검수 중
- `BLOCKED`: 불량·격리 재고
- `IN_TRANSIT`: 입하 중 (아직 창고 미도착)
- `RESERVED`: Wave 피킹 예약됨

### Movement Type (SAP 이동유형)
- `101`: 입고 확정 (RECEIVE)
- `122`: 공급사 반품 (RETURN_TO_SUPPLIER)
- `201`: 출고 (ISSUE_INTERNAL)
- `261`: 생산 출고 (ISSUE_PRODUCTION)
- `311`: 창고 간 이전 (TRANSFER)
- `601`: 배송 출고 (SHIP)
- `701`: 재고 조정+ (ADJUST_PLUS)
- `702`: 재고 조정- (ADJUST_MINUS)

### Stock Type 전환 규칙
```
입하:    없음 → IN_TRANSIT
검수:    IN_TRANSIT → QUALITY_INSPECTION
합격:    QUALITY_INSPECTION → UNRESTRICTED   (Movement 101)
불합격:  QUALITY_INSPECTION → BLOCKED        (격리)
피킹예약: UNRESTRICTED → RESERVED
출고:    RESERVED → 삭제, qty 감소           (Movement 601)
반품:    없음 → BLOCKED (QC_HOLD)
재입고:  BLOCKED → UNRESTRICTED             (Movement 701)
폐기:    BLOCKED → 삭제                     (Movement 702)
```

### 로케이션 ID 체계
- 형식: `{WH}-{ZONE}-{AISLE}-{RACK}-{LEVEL}-{BIN}`
- 예: `WH01-STORAGE-A03-R02-L2-B04`
- Zone 5종: INBOUND_STAGING / QC_HOLD / STORAGE / ASSEMBLY / OUTBOUND_STAGING

### 품목 코드 체계
- 형식: `{CATEGORY}-{SEQ}` (3자리 숫자 패딩)
- CATEGORY: `PKG`(패키징) / `PRD`(생산품) / `ASM`(조립품) / `RAW`(원자재)
- 예: PKG-001, PRD-001, ASM-001, RAW-001

### GR / Wave / RTN 번호 체계
- GR: `GR-YYYYMMDD-NNN`
- Wave: `WAVE-YYYYMMDD-NNN`
- RTN: `RTN-YYYYMMDD-NNN`
- SUP: `SUP-NNN`

## 전문가 에이전트 팀

### 프로젝트 특화 에이전트 (SK 시리즈)

| 에이전트 | 역할 | 키워드 |
|---------|------|--------|
| wms-master-data (SK-01) | 품목·로케이션·공급사 마스터 | 품목코드, 로케이션, 공급사, 바코드, ROP |
| wms-inbound (SK-02) | 입하·검수·입고확정 | 입하, 검수, GR, ASN, AQL, Dock-to-Stock |
| wms-inventory (SK-03) | 재고 원장·트랜잭션·사이클카운팅 | 재고 불일치, 사이클카운팅, 음수재고, ADJUST |
| wms-outbound (SK-04) | Wave·피킹·패킹·출고 | 피킹, 패킹, Wave, SSCC, 출고지시 |
| wms-return (SK-07) | 반품·역물류 | 반품, 역물류, RESTOCK, DISPOSE |

### 라우팅 우선순위
프로젝트 특화(세밀한 키워드) > orchestrator(복합 요청)

## KPI 목표
| KPI | 목표 |
|-----|------|
| Dock-to-Stock | ≤ 8시간 (480분) |
| 피킹 정확도 | ≥ 99.5% |
| 재고 정확도 | ≥ 99% |
| 반품율 | ≤ 0.5% |
| AQL 합격 기준 | 불량률 ≤ 1.0% |

## 태스크 관리
`.claude/feature_list.json` — 전체 태스크 목록 (priority: critical > high > medium > low > done)

## 검증 체크포인트 (코딩 완료 후 필수)

1. **훅 결과 확인**: PostToolUse 훅(typecheck, test-on-change) 오류 없는지 확인
2. **결과 보고**: "typecheck: ✅ / 테스트: ✅ N개 통과" 형식으로 보고
3. **다음 단계 확인**: "다음 단계로 진행할까요?" 물어볼 것
4. **빌드 게이트**: 세션 종료 전 build-gate.sh 자동 실행 (Stop 훅)

### 금지 표현 (검증 없이 사용 불가)
- "완료됐습니다", "구현했습니다" → 훅 결과 없이 사용 금지
- "잘 동작할 것입니다" → 실행 증거 없이 사용 금지

## 병렬 작업 (워크트리)
독립 기능 병렬 개발 시 `/worktree` 커맨드 사용 → `.worktrees/<브랜치명>` 생성

## 실수 학습
반복 실수 발생 시 `/learn` 커맨드 → 이번 세션 실수를 이 파일 하단에 기록
