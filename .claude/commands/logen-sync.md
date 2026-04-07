# /logen-sync — 로젠 운송장 자동 동기화

로젠택배 웹(logis.ilogen.com)의 운송장 출력 완료 페이지에서  
운송장번호를 자동 추출하여 TMS Airtable Shipment 레코드에 저장한다.

---

## 실행 전 체크
- 로젠 운송장 출력 완료 페이지가 브라우저에 열려 있어야 함
- 출력 내용은 동일 페이지 내 iframe(src에 `lrm01f0050` 포함)으로 표시됨

---

## STEP 1 — 브라우저 탭 확인

`mcp__plugin_playwright__browser_tabs` 호출하여 현재 열린 탭 목록 확인.

- `logis.ilogen.com` 포함 탭이 없으면:
  > "로젠 출력 페이지가 열려 있지 않습니다. 로젠 사이트에서 운송장 출력 완료 후 다시 실행해주세요."
  종료.
- 있으면 해당 탭으로 전환(navigate 또는 탭 ID 기준).

---

## STEP 2 — iframe DOM에서 데이터 추출

`mcp__plugin_playwright__browser_evaluate` 호출. 아래 JavaScript 실행:

```javascript
(function() {
  // iframe 찾기: src에 lrm01f0050 포함
  const iframe = Array.from(document.querySelectorAll('iframe'))
    .find(f => f.src && f.src.includes('lrm01f0050'));

  if (!iframe) return { error: 'iframe_not_found' };
  if (!iframe.contentDocument) return { error: 'iframe_access_denied' };

  const doc = iframe.contentDocument;
  const cells = Array.from(doc.querySelectorAll('td, th'));

  const WAYBILL_RE = /^\d{3}-\d{4}-\d{4}$/;
  const ORDER_RE   = /^(TO|MM)\d+/;

  const results = [];
  cells.forEach((cell, idx) => {
    const text = (cell.innerText || '').trim();
    if (!ORDER_RE.test(text)) return;

    const orderNo = text.split('/')[0].trim();

    // 1순위: 같은 tr에서 운송장 탐색
    const row = cell.closest('tr');
    const rowCells = row ? Array.from(row.querySelectorAll('td, th')) : [];
    let waybills = rowCells
      .map(c => (c.innerText || '').trim())
      .filter(t => WAYBILL_RE.test(t));

    // 2순위: 앞 400셀에서 탐색 (same-page grid 레이아웃 대응)
    if (!waybills.length) {
      for (let i = Math.max(0, idx - 400); i < idx; i++) {
        const t = (cells[i]?.innerText || '').trim();
        if (WAYBILL_RE.test(t)) waybills.push(t);
      }
    }

    if (waybills.length) results.push({ orderNo, waybills });
  });

  return { results, total: results.length };
})()
```

**오류 처리:**
- `error: iframe_not_found` → 스냅샷 찍어 페이지 구조 확인 후 사용자에게 안내
- `error: iframe_access_denied` → 브라우저 보안 정책 문제. 직접 접근 불가 시 사용자에게 안내
- `results` 빈 배열 → 추출 결과 없음. 스크린샷으로 페이지 상태 확인

---

## STEP 3 — 데이터 파싱 및 그룹핑

1. 동일 `orderNo`에 대한 waybill 배열 병합 (중복 제거)
2. 하이픈 제거: `"439-7547-9531"` → `"43975479531"`
3. 최종 구조:
   ```
   [
     { orderNo: "TO00015544", waybills: ["43975479531", "43975479542"] },
     { orderNo: "TO00015545", waybills: ["43975479553"] },
   ]
   ```
4. 추출 결과를 사용자에게 먼저 보여주고 확인 요청:
   ```
   추출된 운송장 목록:
   - TO00015544: 43975479531, 43975479542 (2건)
   - TO00015545: 43975479553 (1건)
   
   위 내용을 TMS에 저장할까요? (yes/no)
   ```

---

## STEP 4 — Airtable Shipment 매칭

각 orderNo에 대해 Shipment 레코드 검색.

### 방법 A — Shipment 테이블 직접 검색
```
mcp__claude_ai_Airtable__list_records_for_table
  baseId: app4x70a8mOrIKsMf
  tableId: tbllg1JoHclGYer7m
  filterByFormula: FIND("TO00015544", {배송요청})
  fields: [fldv4U6Gx4d8BWPTb]   ← 운송장번호 필드
```

### 방법 B — Fallback (A 실패 시)
배송요청 테이블 경유:
```
1. mcp__claude_ai_Airtable__list_records_for_table
   baseId: app4x70a8mOrIKsMf
   tableId: tblfIEiPJaEF0DVoM   ← 배송요청 테이블
   filterByFormula: FIND("TO00015544", {logistics_PK})
   fields: [fld1rfeoDNQKASafk]  ← Shipment 링크 필드

2. 링크 필드에서 Shipment record ID 취득
```

**매칭 실패(미매칭):** 에러가 아닌 경보로 기록 후 계속 진행.

---

## STEP 5 — 운송장번호 저장

```
mcp__claude_ai_Airtable__update_records_for_table
  baseId: app4x70a8mOrIKsMf
  tableId: tbllg1JoHclGYer7m
  recordId: (STEP 4에서 취득)
  fields:
    fldv4U6Gx4d8BWPTb: "43975479531 43975479542"  (공백 구분, 하이픈 없는 숫자)
```

**⚠️ 기존 값이 있는 경우:**
- 기존 값을 사용자에게 보여준 뒤 덮어쓰기 여부 확인
- 사용자 승인 시에만 업데이트 진행

---

## STEP 6 — 결과 보고

```
=== /logen-sync 결과 ===

✅ SC00026623 (TO00015544) → 43975479531 43975479542
✅ SC00026624 (TO00015545) → 43975479553
⚠️  TO00015546 → Shipment 매칭 없음 (미배정 또는 취소 주문)
❌ SC00026625 (TO00015547) → 저장 실패 (API 오류)

요약: 3건 처리 / 2건 성공 / 1건 미매칭 / 1건 실패
```

---

## Airtable 필드 레퍼런스

| 항목 | ID |
|------|-----|
| TMS Base | `app4x70a8mOrIKsMf` |
| Shipment 테이블 | `tbllg1JoHclGYer7m` |
| Shipment.운송장번호 | `fldv4U6Gx4d8BWPTb` |
| 배송요청 테이블 | `tblfIEiPJaEF0DVoM` |
| 배송요청.Shipment 링크 | `fld1rfeoDNQKASafk` |

---

## 운송장번호 형식

| 입력 | 저장 |
|------|------|
| `439-7547-9531` | `43975479531` |
| `440-4299-7880` | `44042997880` |
| 여러 개 | `43975479531 43975479542` (공백 구분) |
