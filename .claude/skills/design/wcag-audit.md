---
name: wcag-audit
description: WCAG 2.1 AA 접근성 감사 절차. UI 컴포넌트/페이지의 접근성 검증에 사용.
---

# WCAG 2.1 AA 접근성 감사 절차

> **대상:** 웹 UI 컴포넌트 및 페이지
> **참조:** WCAG 2.1 Level AA, WAI-ARIA 1.2
> **원칙:** Perceivable, Operable, Understandable, Robust (POUR)

## Step 1: 색상 대비 검사

| 기준 | 비율 | WCAG 번호 |
|------|------|-----------|
| 일반 텍스트 (< 18px) | 4.5:1 이상 | 1.4.3 |
| 큰 텍스트 (>= 18px bold / 24px) | 3:1 이상 | 1.4.3 |
| UI 컴포넌트/그래픽 | 3:1 이상 | 1.4.11 |

검사 방법: Chrome DevTools > Accessibility > Contrast ratio

## Step 2: 키보드 접근성 검사

- [ ] Tab 키로 모든 인터랙티브 요소에 접근 가능 (2.1.1)
- [ ] 포커스 인디케이터가 시각적으로 보임 (2.4.7)
- [ ] 키보드 트랩 없음 -- Escape로 모달 닫기 가능 (2.1.2)
- [ ] Tab 순서가 논리적 (2.4.3)

## Step 3: 시맨틱 HTML 검사

- [ ] 제목 계층 올바름 (h1 → h2 → h3, 건너뛰기 없음)
- [ ] 랜드마크 역할 사용 (header, nav, main, footer)
- [ ] 폼 요소에 label 연결 (for/id 또는 aria-label)
- [ ] 이미지에 alt 텍스트 (장식 이미지는 alt="")
- [ ] 버튼/링크 구분 명확 (링크=이동, 버튼=동작)

## Step 4: ARIA 검사

- [ ] role 속성이 올바르게 사용되었는가
- [ ] aria-label / aria-labelledby 누락 없는가
- [ ] aria-expanded, aria-selected 등 상태 속성이 동적으로 업데이트되는가
- [ ] 라이브 리전(aria-live)이 동적 콘텐츠에 적용되어 있는가

## Step 5: 반응형/모바일 검사

- [ ] 200% 확대 시 콘텐츠 잘림 없음 (1.4.4)
- [ ] 터치 타겟 최소 44x44px
- [ ] 가로 스크롤 없음 (320px 뷰포트에서)

## 검증

```bash
# Lighthouse 접근성 점수 확인
npx lighthouse {URL} --only-categories=accessibility --output=json
```

## 주의사항

- aria 속성을 남용하지 말 것 -- 시맨틱 HTML이 우선
- "스크린리더로 직접 테스트" 대체 불가 (NVDA, VoiceOver)
