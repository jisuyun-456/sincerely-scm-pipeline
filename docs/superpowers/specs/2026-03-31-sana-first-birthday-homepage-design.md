# Sana's First Birthday Homepage — Design Spec

## Context

딸아이(윤사나 / Sana Yun) 첫 돌(2026-05-24)을 기념하는 프리미엄 미니 홈페이지 제작.
Apple/Anthropic 수준의 디자인 퀄리티를 목표로 하며, 두 개의 사이트를 제작한다:
1. **돌잔치 초대 + 성장 기록** — 행사 안내 겸 성장 타임라인
2. **추억 보관용 아카이브** — 장기 보관 디지털 앨범

## Design Direction

**Gradient Glow + Cinematic Scroll**

- 기반: Anthropic 홈페이지 스타일 — 딥 다크 배경(`#0a0a0a` ~ `#0f0c29`) + 보라/핑크 그라데이션 글로우
- 인터랙션: Apple 제품 페이지 스타일 — GSAP ScrollTrigger 기반 시네마틱 스크롤 애니메이션
- 사진이 빛 속에서 떠오르는 몽환적 경험

## Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Framework | Next.js 15 (App Router) | React 기반, SSG 지원, Vercel 최적화 |
| Styling | Tailwind CSS 4 | 유틸리티 기반 빠른 스타일링 |
| Animation | Framer Motion + GSAP ScrollTrigger | 스크롤 기반 시네마틱 애니메이션 |
| Font | Inter (영문) + Noto Serif KR (한글) | 프리미엄 타이포 조합 |
| Deploy | Vercel | 무료, 자동 배포, CDN, 커스텀 도메인 |
| Image | Next.js Image + Vercel Image Optimization | 자동 WebP/AVIF, lazy loading |

## Site 1: 돌잔치 초대 + 성장 기록

원페이지 스크롤 구조. 모바일 반응형 필수.

### Section 01 — Hero

- **레이아웃**: 풀스크린(100vh) 다크 배경
- **콘텐츠**:
  - "사나" — Noto Serif KR, 72px+, linear-gradient 글로우 텍스트 (`#fff → #c8b0ff → #ffb8d0`)
  - "SANA YUN" — Inter, 14px, letter-spacing 8px, `rgba(255,255,255,0.3)`
  - "The First 365 Days" — 태그라인
  - 날짜 배지: `★ 2026. 05. 24`
- **배경**:
  - `linear-gradient(135deg, #0f0c29, #302b63, #24243e)`
  - 위에 radial-gradient 글로우 오브 2~3개 (보라/파랑/핑크)
  - 선택적: CSS or Three.js 파티클 (성능 고려하여 CSS 우선)
- **애니메이션**:
  - 이름: 0.8s fade-in + slight scale
  - 배경 그라데이션: 느린 색상 시프트 (CSS animation, 20s cycle)
  - 스크롤 시: 콘텐츠 패럴렉스 줌아웃 + opacity fade
  - 하단: "↓ SCROLL TO EXPLORE" 펄스 애니메이션

### Section 02 — Story Timeline (월별 성장 기록)

- **레이아웃**: 세로 스크롤, 월별 카드 리스트
- **각 카드 구성**:
  - 왼쪽: 월 숫자 (32px, 보라 글로우) + 월명
  - 오른쪽: 대표 사진 1장 (80x80, rounded-lg) + 제목 + 짧은 에피소드 텍스트
  - 카드 배경: `rgba(255,255,255,0.02)`, border `rgba(255,255,255,0.05)`, rounded-xl
- **데이터**: 12개월 × (사진 URL, 제목, 설명) — `src/data/timeline.ts`에 정적 배열
- **애니메이션**:
  - 카드: 스크롤 진입 시 stagger fade-in (각 0.15s 딜레이)
  - 배경: 스크롤 위치에 따라 그라데이션 hue 미묘한 변화
  - 호버: 카드 border glow + slight lift

### Section 03 — Gallery (시네마틱 포토)

- **레이아웃**: 벤토 그리드 (CSS Grid)
  - 첫 번째 사진: `grid-column: span 2`, 가로로 크게
  - 나머지: 1:1 or 4:3 비율 혼합
  - 모바일: 2열 그리드로 변환
- **인터랙션**:
  - 스크롤 진입 시 사진 scale(0.9→1) + opacity(0→1) reveal
  - 호버: 글로우 오버레이 + 캡션 텍스트 슬라이드업
  - 클릭: 풀스크린 라이트박스 (Framer Motion layoutId transition)
- **사진**: 10~20장, Next.js Image로 최적화

### Section 04 — Invitation (돌잔치 안내)

- **레이아웃**: 중앙 정렬, 글래스모피즘 카드 (max-w-md)
- **카드 스타일**:
  - `backdrop-filter: blur(8px)`
  - `background: rgba(255,255,255,0.03)`
  - `border: 1px solid rgba(255,255,255,0.06)`
  - rounded-2xl, padding 32px
- **콘텐츠**:
  - 아이콘: 💌
  - 제목: "돌잔치에 초대합니다"
  - 설명: "사나의 첫 번째 생일을 함께 축하해주세요"
  - 정보 그리드 (2×2):
    - 날짜: 2026. 05. 24 (일)
    - 시간: (추후 확정)
    - 장소: (추후 확정)
    - 지도: 카카오맵 링크 버튼
- **애니메이션**: 카드 slide-up on scroll

### Section 05 — Footer

- 심플 한 줄: "Made with ♥ by 윤 Family"
- 스타일: `#08080a` 배경, `#444` 텍스트, 12px

## Site 2: 추억 보관용 아카이브

같은 Gradient Glow 디자인 시스템을 공유하되, 초대 섹션을 제거하고 갤러리/기록에 집중.

### 구조

1. **Hero** — Site 1과 동일한 스타일, "Sana's Archive" 태그라인 변경
2. **월별 포토 갤러리** — 각 월 탭/섹션에 무제한 사진 업로드 가능
3. **성장 기록** — 키/몸무게/이정표 타임라인
4. **가족 메시지 보드** — 가족이 메시지를 남길 수 있는 공간
5. **Footer** — Site 1과 동일

### 구현 단계

- **1차 (MVP)**: 모든 데이터를 정적 파일(`src/data/`)로 관리. 사진은 `public/images/`에 직접 배치. 메시지 보드는 하드코딩된 샘플 메시지로 시작.
- **2차 (확장)**: 필요 시 Supabase 등 백엔드 연동하여 사진 업로드, 메시지 작성 기능 추가.

### Site 1 → Site 2 연결

- Site 1 Footer에 "Archive 보러가기 →" 링크
- Site 2 Hero에 "돌잔치 초대장 보러가기 →" 링크
- 같은 Vercel 프로젝트 내 별도 경로 (`/` = 초대장, `/archive` = 아카이브) 또는 별도 서브도메인

## Design Tokens

```
Colors:
  background:     #0a0a0a
  surface:        rgba(255,255,255,0.02)
  border:         rgba(255,255,255,0.05)
  border-hover:   rgba(200,140,255,0.15)
  text-primary:   #fafafa
  text-secondary: rgba(255,255,255,0.5)
  text-muted:     #555
  glow-purple:    #c8b0ff
  glow-pink:      #ffb8d0
  glow-blue:      #80b0ff
  accent:         linear-gradient(135deg, #fff, #c8b0ff, #ffb8d0)

Typography:
  heading-kr:     'Noto Serif KR', serif — weight 300/400
  heading-en:     'Inter', sans-serif — weight 200/300
  body:           'Inter', sans-serif — weight 300/400

Spacing:
  section-gap:    120px (desktop) / 80px (mobile)
  content-max:    1100px
  card-padding:   24px ~ 32px
  card-radius:    12px ~ 16px

Breakpoints:
  mobile:         < 768px
  tablet:         768px ~ 1024px
  desktop:        > 1024px
```

## Project Structure

```
sana-first-birthday/
├── src/
│   ├── app/
│   │   ├── layout.tsx          # 글로벌 레이아웃, 폰트, 메타데이터
│   │   ├── page.tsx            # Site 1: 돌잔치 초대 + 성장 기록
│   │   └── archive/
│   │       └── page.tsx        # Site 2: 추억 보관용 아카이브
│   ├── components/
│   │   ├── Hero.tsx
│   │   ├── StoryTimeline.tsx
│   │   ├── Gallery.tsx
│   │   ├── Invitation.tsx
│   │   ├── Footer.tsx
│   │   ├── Lightbox.tsx
│   │   └── GradientBackground.tsx
│   ├── data/
│   │   └── timeline.ts         # 월별 데이터 (사진 URL, 제목, 설명)
│   └── styles/
│       └── globals.css         # Tailwind base + custom CSS animations
├── public/
│   └── images/                 # 사진 파일
├── tailwind.config.ts
├── next.config.ts
└── package.json
```

## Mobile Responsiveness

- Hero: 이름 font-size 48px (모바일) / 72px (데스크톱)
- Timeline: 카드 세로 풀폭, 월 숫자 상단 배치
- Gallery: 2열 그리드 (모바일) / 3열 벤토 (데스크톱)
- Invitation: 카드 풀폭, 정보 그리드 1열
- 터치 디바이스: 호버 효과 대신 탭 인터랙션

## Performance Targets

- Lighthouse Performance: 90+
- LCP: < 2.5s
- CLS: < 0.1
- Next.js Image로 자동 WebP/AVIF 변환
- GSAP/Framer Motion 번들: 트리쉐이킹으로 최소화
- 선택적: `prefers-reduced-motion` 미디어쿼리로 애니메이션 비활성화

## Verification

1. `npm run build` — SSG 빌드 성공 확인
2. `npm run dev` — 로컬에서 모바일/데스크톱 모두 확인
3. Lighthouse 감사 — Performance 90+ 확인
4. 실제 모바일 기기에서 URL 접근 및 스크롤 테스트
5. Vercel 배포 후 공유 URL 동작 확인
