# PDF 생성 파이프라인 방법론

## 아키텍처
```
Airtable Automation 트리거
  → Make Scenario (webhook)
  → GitHub Actions (workflow_dispatch: generate_pdf.yml)
  → Python reportlab 렌더링
  → GitHub Releases 업로드
  → Airtable attachment API 역첨부
```

## 한글 폰트 처리

```python
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

pdfmetrics.registerFont(TTFont('Pretendard', 'fonts/Pretendard-Regular.ttf'))
pdfmetrics.registerFont(TTFont('Pretendard-Bold', 'fonts/Pretendard-Bold.ttf'))
# NanumGothic 필요 시 추가 등록
```

폰트 파일 위치: sincerely-scm-pipeline-github 레포 내 tms/fonts/

## Airtable 중첩 필드 추출

Airtable Linked Record 필드는 valuesByLinkedRecordId 구조로 반환된다.
직접 .fields 접근 시 데이터 누락 발생.

```python
# 올바른 추출 방법
linked_data = field.get("valuesByLinkedRecordId", {})
values = list(linked_data.values())[0] if linked_data else []

# 잘못된 방법 (데이터 누락)
values = field.get("value")  # None 반환됨
```

## 문서 종류

### 출고확인서 (delivery_confirmation)
- 출고 시 발행
- 내용: 출고일, 품목, 수량, 위치, 수령인
- 템플릿: tms/templates/delivery_confirmation.py (pipeline 레포)

### 거래명세서 (transaction_statement)
- 거래처 전용
- 내용: 거래일, 품목별 단가/수량/금액, 합계
- 템플릿: tms/templates/transaction_statement.py (pipeline 레포)

## GitHub Actions 워크플로우 (generate_pdf.yml)

트리거: workflow_dispatch (Make에서 호출)
입력 파라미터: record_id, document_type
환경변수: AIRTABLE_PAT, GITHUB_TOKEN (Secrets)

## 주의사항
- Python 파일에 이모지/특수문자(스마트쿼트, em dash) 절대 금지
- 모바일 GitHub 편집 시 자동 스마트쿼트 삽입됨 → 데스크탑에서만 편집
- Airtable attachment API 업로드 시 URL 만료 주의 (GitHub Releases URL은 영구)
- reportlab의 Paragraph 사용 시 HTML 엔티티 이스케이프 필요 (<, > 등)
