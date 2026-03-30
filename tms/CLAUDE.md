# TMS — 운송관리 모듈

## 핵심 문서
- 출고확인서: 출고 시 발행 (reportlab PDF)
- 거래명세서: 거래처 전용 (reportlab PDF, Pretendard 폰트)

## PDF 파이프라인
Airtable Automation → Make webhook → GitHub Actions(generate_pdf.yml) → Python reportlab → GitHub Releases → Airtable attachment

## 폰트
Pretendard-Regular/Bold, NanumGothic. 경로: tms/fonts/ (pipeline 레포 내)

## Logen 택배 연동
Chrome Extension(logen-tms-extension/) — IBSheet DOM 이슈로 bookmarklet 불가하여 extension 구현

## CBM 산출
우선순위: 수동입력 → Product 테이블 매칭(83.4%) → 박스 문자열 파싱 → 미산출 0.0
매칭 실패율 16.6% — 변형 표기, 미등록 품목이 원인

## OTIF KPI
On Time: 약속 배송일 기준 / In Full: 요청 수량 대비 실배송 수량
