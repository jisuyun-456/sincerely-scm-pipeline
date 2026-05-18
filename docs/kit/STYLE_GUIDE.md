# 문서형 HTML — Style Guide

> `_template.html` + `doc.css`를 베이스로 모든 문서를 작성한다.
> 새 문서를 만들 때마다 **반드시** 이 가이드를 그대로 따른다.

---

## 1. 출력 규칙 (요약)

새 문서를 만들 때:

1. `_template.html`을 그대로 복사해서 새 파일을 만든다.
2. **같은 폴더에 서빙하는 경우**: `<link rel="stylesheet" href="doc.css" />`로만 참조.
   **단독 파일로 공유하는 경우**: CSS를 인라인 `<style>`로 포함 (doc.css 전체 내용 복사).
3. 파일명은 `{문서명} (문서형).html` 형식 (예: `물류비 분석 (문서형).html`).
4. 한자(漢字)는 절대 사용하지 않는다. 모든 텍스트는 한글 + 영문 + 숫자만.
5. 챕터 번호는 로마 숫자(I, II, III, …)로 표기한다. `<span class="nm">II</span>` 형식.
6. 폰트는 **Newsreader (serif)** + **Pretendard (sans)** + **JetBrains Mono** 세 가지만 사용.
7. 이모지 사용 금지.

---

## 2. 페이지 구조 (3-Column)

```
── topbar ──────────────────────────────────────────
  로고  /  문서명                    ID · 버전 · 일자
────────────┬──────────────────────────┬────────────
            │                          │            
  좌측      │     article 본문          │  우측 TOC  
  챕터      │     (max 720px)          │  (소제목)  
  목차      │                          │            
            │                          │            
────────────┴──────────────────────────┴────────────
```

- **좌측 nav** (`aside.side`) → 챕터 단위 (로마 숫자 I, II, III…)
- **본문** (`article`) → 최대 720px. 절대 더 넓히지 않는다.
- **우측 TOC** (`aside.toc`) → 같은 문서 내 h2/h3 소항목. 1040px 이하에서 자동 숨김.

---

## 3. 상단 메타

```html
<div class="topbar">
  <div class="mark"><div class="dot">{2글자}</div> {프로젝트명}</div>
  <span class="sep">/</span>
  <span class="doc-name">{문서명}</span>
  <div class="right">
    <span>{문서ID}</span>
    <span class="ver">{버전} · {YY.MM.DD}</span>
  </div>
</div>
```

- 로고 dot은 2글자 약어(예: MH, SC). 항상 검정 원 + 흰 모노폰트.
- 버전은 `v0.1`, `Iter 1.4` 같은 형식. 날짜는 `26.05.18` 2자리.

---

## 4. 문서 헤더 (article 첫 블록)

```html
<div class="eyebrow">{영문 분류 · UPPER CASE}</div>
<h1>{문서 제목}</h1>
<p class="lede">{한 줄 요약 — 이 문서가 무엇인지}</p>
<div class="byline">
  <span><span class="k">작성일</span>YYYY.MM.DD</span>
  <span><span class="k">기준</span>{버전}</span>
  <span><span class="k">용도</span>{사용 목적}</span>
</div>
```

- `eyebrow`는 영문 대문자, 1줄. (예: `INTEGRATED BRIEF · M/H MEASUREMENT DESIGN`)
- `lede`는 이탤릭 serif. **반드시 한 문장**.
- `byline`은 메타 4개 이내. mono 폰트.

---

## 5. 챕터 (h2)

```html
<h2 id="chA"><span class="nm">II</span>챕터 제목</h2>
```

- `id`는 `ch0`, `chA`, `chB` … 알파벳 순.
- `<span class="nm">` 안에 로마 숫자(I, II, III, …).
- 챕터 첫 단락은 dropcap, 그 다음에 컴포넌트.

---

## 6. 컴포넌트 라이브러리

### 6.1 정의 리스트 — `dl.def`
용어 / 라벨 → 설명 매핑. 2-column 그리드.
```html
<dl class="def">
  <div><dt>용어<br><span style="color:var(--muted-2);font-size:11px">English</span></dt><dd>설명.</dd></div>
</dl>
```

### 6.2 수식 박스 — `.formula`
공식 한 줄. FORMULA 라벨이 자동으로 붙는다.
```html
<div class="formula">
  Standard Time = ( A + B ) × ( 1 + <span class="c">변수</span> )
</div>
```
- `<span class="c">` → 강조 변수 (accent 색).
- `<span class="em">` → 노란 하이라이트.

### 6.3 표 — `.tbl`
5가지 그리드 옵션: `c2` `c3` `c3-wide` `c3-num` `c4`.
```html
<div class="tbl c3-wide">
  <div class="r h"><div>필드</div><div>기준</div><div>비고</div></div>
  <div class="r">
    <div><strong>항목</strong></div>
    <div class="mono">값</div>
    <div>비고</div>
  </div>
</div>
```
- 헤더 행은 `class="r h"`.
- 숫자/코드 셀에 `class="mono"`.
- 우측정렬 숫자는 `class="num"`, 합계 행은 추가로 `class="total"`.

### 6.4 노트 박스 — `.note`
3가지 타입: 기본 / `.warn` / `.accent`.
```html
<div class="note warn">
  <div class="tag">라벨</div>
  <div class="body">본문. <strong>강조.</strong></div>
</div>
```

### 6.5 풀쿼트 — `.pullquote`
챕터 도입부 핵심 한 줄.
```html
<div class="pullquote">
  핵심 메시지 한 문장.
  <cite>출처</cite>
</div>
```

### 6.6 출처 라인 — `.src`
표 바로 아래 dashed 박스.
```html
<div class="src"><strong>출처</strong> · WERC · SAP EWM.</div>
```

### 6.7 태그 — `.tag-pill`
인라인 라벨. 기본 / `.solid` / `.warn` / `.accent`.
```html
<span class="tag-pill solid">기준 이상</span>
```

### 6.8 개념 카드 3개 — `.concepts > .concept`
3개 짜리 횡렬 카드. 우상단에 흐릿한 번호.
```html
<div class="concepts">
  <div class="concept">
    <span class="n">01</span>
    <div class="t">제목<span class="sub">SUB LABEL</span></div>
    <p style="margin:0;font-size:13.5px">본문.</p>
  </div>
</div>
```

### 6.9 로드맵 — `.roadmap > .road-row`
세로 타임라인. 좌측 검정 박스 + 우측 설명.
```html
<div class="roadmap">
  <div class="road-row">
    <div class="v">Iter 1.5</div>
    <div class="d"><strong>제목</strong>설명.</div>
  </div>
</div>
```

### 6.10 인라인 코드
`<code class="inl">snippet</code>` → 회색 배경 + 보더.

### 6.11 코드 블록 — `pre.code`
공식·예시·의사코드 블록. `.c` 강조(accent 색), `.h` 주석(muted).
```html
<pre class="code">M/H = CBM × 4.0 × PFD(1.15)

<span class="h"># 예시</span>
CBM 10 → 46분 = <span class="c">0.77 MH</span></pre>
```

### 6.12 숫자 카드 — `.stats > .stat`
도입부 핵심 수치 3개를 횡렬로. 1040px 이하에서 1열로 떨어짐.
```html
<div class="stats">
  <div class="stat">
    <div class="k">현재 가동률</div>
    <div class="v">20.8<span class="unit">%</span></div>
    <div class="sub">184.6 MH / 886 MH 가용</div>
  </div>
</div>
```

### 6.13 흐름도 — `.flow`
화살표로 이어지는 단선 흐름. mono 폰트, `→`는 `<span class="arr">→</span>`.
```html
<div class="flow">
<strong>시작</strong>
  <span class="arr">→</span> 단계 1
  <span class="arr">→</span> 단계 2
  <span class="arr">→</span> <strong>결과</strong>
</div>
```

### 6.14 트리 다이어그램 — `.tree`
계층 구조. ASCII 트리(`├──`, `└──`) 그대로 사용.
```html
<div class="tree">
<strong>root</strong> <span class="l">→ 설명</span>
    │
    ├── <strong>child A</strong> <span class="l">→ 설명</span>
    └── <strong>child B</strong> <span class="l">→ 설명</span>
</div>
```

### 6.15 숫자 표 — `.tbl.c3-num`
공정/건수/MH 같은 집계 표. `.num` 우측정렬, `.total` 합계 행.
```html
<div class="tbl c3-num">
  <div class="r h"><div>공정</div><div style="text-align:right">건수</div><div style="text-align:right">MH</div></div>
  <div class="r"><div>입하</div><div class="num">1,034 건</div><div class="num">44.8</div></div>
  <div class="r"><div class="total">합계</div><div class="num total">—</div><div class="num total">184.6</div></div>
</div>
```

---

## 7. 본문 작성 팁

- 단락은 짧게, 한 단락당 2~4문장.
- 한국어 본문 안의 영문 키워드는 그대로 이어진다 (예: "Touch time").
- 강조는 `<strong>` 만 사용. `<b>`, 대문자 강조 금지.
- 이탤릭은 `<em>` (serif 폰트로 자동 전환됨).
- 영문 약어는 첫 등장 시 풀어준다. (예: `PFD (Personal + Fatigue + Delay)`)
- 숫자 범위는 `50 ~ 150` 형식 (앞뒤 공백).
- 코드/예시는 `<code class="inl">…</code>`.

---

## 8. 색 / 타입 토큰

CSS 변수에 정의되어 있다. **새 변수를 추가하지 말 것.**

| 변수 | 용도 |
|------|------|
| `--ink` | 본문 텍스트 / 강조 보더 |
| `--ink-2` | 본문 보조 텍스트 |
| `--muted` | 메타 / 라벨 |
| `--muted-2` | 가장 약한 라벨 |
| `--line` | 일반 보더 |
| `--accent` | 링크 / 강조 색 (남색) |
| `--warn` | 경고 라벨 (브라운) |
| `--highlight` | 노란 하이라이트 |
| `--surface-2` | 카드/박스 배경 |

---

## 9. 인쇄 (PDF 변환)

- `@media print`가 좌/우 사이드바를 자동으로 숨김.
- A4 출력 시 본문이 페이지 전체 폭으로 펼쳐진다.
- `.formula`, `.concept`, `.road-row`, `.tbl`, `.stat`, `.flow`, `.tree`, `pre.code`에 페이지 분할 방지 적용됨.

---

## 10. 새 문서를 만들 때 체크리스트

- [ ] `_template.html`을 복사했는가
- [ ] 한자가 들어가지 않았는가
- [ ] 챕터 번호가 로마 숫자인가
- [ ] 본문 max-width 720px 유지하고 있는가
- [ ] 좌측 nav · 우측 TOC 둘 다 챕터와 일치하는가
- [ ] eyebrow 영문 · lede 한 문장 · byline 4개 이내인가
- [ ] 새 변수나 새 폰트를 추가하지 않았는가
- [ ] 이모지가 없는가
