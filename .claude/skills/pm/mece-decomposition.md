---
name: mece-decomposition
description: MECE 원칙에 따른 문제 분해 절차. 구조화된 분석이 필요할 때 사용.
---

# MECE 분해 절차

> **대상:** 복잡한 문제/주제를 구조화할 때
> **참조:** McKinsey Problem Solving, Barbara Minto Pyramid Principle
> **원칙:** Mutually Exclusive (중복 없음), Collectively Exhaustive (누락 없음)

## Step 1: 핵심 질문 정의

"해결해야 할 질문(Key Question)을 한 문장으로 정리"

- 너무 넓으면 → 범위를 좁혀 재정의
- 너무 좁으면 → 상위 질문에서 시작

## Step 2: 1차 분해 (Top-Level Branches)

핵심 질문을 3~7개 하위 항목으로 분해.

**MECE 검증:**
- [ ] 각 항목이 서로 겹치지 않는가? (ME)
- [ ] 모든 항목을 합치면 전체를 커버하는가? (CE)

**분해 프레임워크 선택:**
| 프레임워크 | 적용 | 예시 |
|-----------|------|------|
| 프로세스 순서 | 시간 흐름 | 입고→검수→적치→피킹→출하 |
| 구성요소 | 부분의 합 | 매출=단가x수량x고객수 |
| 관점별 | 이해관계자 | 고객/공급사/내부 |
| 대안별 | 의사결정 | 옵션A/B/C |

## Step 3: 2차 분해 (각 Branch를 세분화)

- 최대 3단계 깊이까지만 (깊어지면 복잡성 폭발)
- 각 단계에서 MECE 검증 반복

## Step 4: Issue Tree 완성

```
Key Question
├── Branch 1
│   ├── Sub 1-1
│   └── Sub 1-2
├── Branch 2
│   ├── Sub 2-1
│   └── Sub 2-2
└── Branch 3
    ├── Sub 3-1
    └── Sub 3-2
```

## Step 5: 우선순위 부여

| 기준 | High | Medium | Low |
|------|------|--------|-----|
| Impact | 핵심 질문 해결에 직접 기여 | 간접 기여 | 미미한 영향 |
| Feasibility | 즉시 착수 가능 | 조건부 | 장기 |

## 검증

- [ ] 모든 leaf node가 "분석 가능한" 수준인가?
- [ ] MECE가 깨진 곳은 없는가?
- [ ] Pyramid Principle로 결론→근거→데이터 역순 검증 가능한가?
