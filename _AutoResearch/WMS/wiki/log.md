# WMS AutoResearch — Session Log

---

## [2026-04-21] SETUP | program.md 초기화 + 주간 러너 구성

**타입:** Setup  
**상태:** 완료

### 완료 항목
- `program.md` 작성 (3 KPI, 4 Iteration 계획)
- `_AutoResearch/WMS/` 디렉토리 구조 생성
- `scripts/wms_weekly_runner.py` 작성
- `.github/workflows/wms-weekly-autoresearch.yml` 등록

### 분석 대상 확정
- **QC 불량 proxy**: `order.표본 검수 결과` (singleSelect) 불합격 카운트 + `movement.검수 status` 텍스트 파싱
- **입출고 볼륨 트렌드**: `movement.이동목적` × `movement.생성일자` 주간 집계
- **공급사 납기 proxy**: `order.입고예정일` vs `order.실제 입고일` diff (공급사별 그룹핑)

### 다음 단계
1. GitHub Actions 수동 trigger → 첫 번째 WMS weekly 리포트 생성 확인
2. Iter 1 baseline 분석 시작

## [2026-04-21] WEEKLY | 주간 분석 2026-W16

**상태:** 완료

### KPI 스냅샷
- QC 불량 proxy: 0.0% (텍스트 파싱)
- 입출고 볼륨: 13건 (WoW -68건)
- 공급사 평균 납기 편차: 측정 불가

### 산출물
- [WMS-2026-W16.md](../outputs/WMS-2026-W16.md)

### 다음 주 포커스
- 납기 지연 공급사 지속 모니터링

## [2026-04-21] WEEKLY | 주간 분석 2026-W16

**상태:** 완료

### KPI 스냅샷
- QC 불량 proxy: 0.0% (텍스트 파싱)
- 입출고 볼륨: 13건 (WoW -68건)
- 공급사 평균 납기 편차: 측정 불가

### 산출물
- [WMS-2026-W16.md](../outputs/WMS-2026-W16.md)

### 다음 주 포커스
- 납기 지연 공급사 지속 모니터링

## [2026-04-21] WEEKLY | 주간 분석 2026-W16

**상태:** 완료

### KPI 스냅샷
- QC 이슈 proxy: 4.8% (176/3656건) (생산산출+재고생산 중 이슈카테고리 발생률)
- 입출고 볼륨: 18건 (WoW -63건)
- 미입하 발생이력: 87건

### 산출물
- [WMS-2026-W16.md](../outputs/WMS-2026-W16.md)

### 다음 주 포커스
- 납기 지연 공급사 지속 모니터링
