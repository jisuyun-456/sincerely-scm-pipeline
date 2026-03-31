// ==UserScript==
// @name         로젠 → TMS 운송장 자동 전송
// @namespace    sincerely-scm
// @version      1.3
// @description  로젠택배 그리드의 운송장번호를 Airtable TMS Shipment에 자동 업데이트
// @match        https://logis.ilogen.com/*
// @all-frames
// @run-at       document-end
// @grant        GM_xmlhttpRequest
// @connect      api.airtable.com
// ==/UserScript==

(function () {
  'use strict';

  // ─── 설정 ────────────────────────────────────────────────────────────
  const CONFIG = {
    TOKEN: 'patU9ew1rwbJbEpOn.d5c7c1bb42c3ad69edd2701ee0424ddcb04c4d261a0ed422f8e5edaf1fa20edc',
    BASE: 'app4x70a8mOrIKsMf',
    TABLE_TO: 'tblfIEiPJaEF0DVoM',       // 배송요청 테이블
    FLD_TO_SHIPMENT: 'fld1rfeoDNQKASafk', // 배송요청.Shipment 링크 필드
    TABLE_SC: 'tbllg1JoHclGYer7m',       // Shipment 테이블
    FLD_TRACKING: 'fldv4U6Gx4d8BWPTb',   // Shipment.운송장번호 필드
  };

  const BTN_ID = 'tms-tracking-btn-wrapper';

  // ─── Airtable API 헬퍼 ───────────────────────────────────────────────
  function atFetch(method, urlPath, body) {
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        method,
        url: `https://api.airtable.com/v0/${CONFIG.BASE}/${urlPath}`,
        headers: {
          Authorization: `Bearer ${CONFIG.TOKEN}`,
          'Content-Type': 'application/json',
        },
        data: body ? JSON.stringify(body) : undefined,
        onload: (res) => {
          if (res.status >= 200 && res.status < 300) {
            resolve(JSON.parse(res.responseText));
          } else {
            reject(new Error(`Airtable ${res.status}: ${res.responseText}`));
          }
        },
        onerror: (err) => reject(new Error('네트워크 오류: ' + JSON.stringify(err))),
      });
    });
  }

  // ─── 그리드 파싱 ────────────────────────────────────────────────────
  // 핵심 수정: thead/tbody를 분리해서 헤더와 데이터 행을 올바르게 구분
  function parseGrid() {
    const map = {};

    for (const table of document.querySelectorAll('table')) {
      let trackingIdx = -1;
      let itemIdx = -1;

      // 1) thead 안의 th 먼저 탐색
      const theadCells = table.querySelectorAll('thead th, thead td');
      if (theadCells.length > 0) {
        theadCells.forEach((cell, idx) => {
          const text = cell.innerText.trim();
          if (text === '운송장번호') trackingIdx = idx;
          if (text === '물품명') itemIdx = idx;
        });
      }

      // 2) thead가 없으면 첫 번째 tr의 th/td로 탐색
      if (trackingIdx === -1) {
        const firstRow = table.querySelector('tr');
        if (firstRow) {
          firstRow.querySelectorAll('th, td').forEach((cell, idx) => {
            const text = cell.innerText.trim();
            if (text === '운송장번호') trackingIdx = idx;
            if (text === '물품명') itemIdx = idx;
          });
        }
      }

      if (trackingIdx === -1 || itemIdx === -1) continue;

      console.log(`[TMS] 그리드 발견 — 운송장번호 col:${trackingIdx}, 물품명 col:${itemIdx}`);

      // 3) 데이터 행 수집: tbody 있으면 tbody tr, 없으면 tr 전체에서 첫 행 제외
      const bodyRows = table.querySelector('tbody')
        ? Array.from(table.querySelectorAll('tbody tr'))
        : Array.from(table.querySelectorAll('tr')).slice(1);

      for (const tr of bodyRows) {
        const tds = tr.querySelectorAll('td');
        if (tds.length <= Math.max(trackingIdx, itemIdx)) continue;

        const tracking = tds[trackingIdx].innerText.trim();
        const itemName = tds[itemIdx].innerText.trim();

        // 운송장번호 형식: 440-4299-7880
        if (!tracking || !/^\d{3}-\d{4}-\d{4}$/.test(tracking)) continue;
        // 물품명이 TO로 시작하고 / 포함
        if (!itemName.startsWith('TO') || !itemName.includes('/')) continue;

        const toNumber = itemName.split('/')[0].trim(); // "TO00015767"
        if (!map[toNumber]) map[toNumber] = [];
        if (!map[toNumber].includes(tracking)) map[toNumber].push(tracking);
      }

      // 테이블을 찾았으면 첫 번째 결과 사용
      if (Object.keys(map).length > 0) break;
    }

    console.log('[TMS] parseGrid 결과:', map);
    return Object.keys(map).length > 0 ? map : null;
  }

  // ─── 1건 처리 ────────────────────────────────────────────────────────
  async function syncOne(toNumber, trackingNumbers) {
    // 배송요청 테이블에서 TO 번호로 레코드 검색
    const encoded = encodeURIComponent(`FIND("${toNumber}", {logistics_PK})`);
    const toRes = await atFetch(
      'GET',
      `${CONFIG.TABLE_TO}?filterByFormula=${encoded}&fields[]=${CONFIG.FLD_TO_SHIPMENT}`
    );

    console.log(`[TMS] ${toNumber} 조회 결과:`, toRes);

    if (!toRes.records || toRes.records.length === 0) {
      return { ok: false, reason: 'TMS에서 배송요청 레코드를 찾을 수 없음' };
    }

    const shipmentLinks = toRes.records[0].fields[CONFIG.FLD_TO_SHIPMENT];
    if (!shipmentLinks || shipmentLinks.length === 0) {
      return { ok: false, reason: '배송요청에 연결된 Shipment 레코드 없음' };
    }

    const shipmentId = shipmentLinks[0];
    console.log(`[TMS] ${toNumber} → Shipment ID: ${shipmentId}, 운송장: ${trackingNumbers}`);

    await atFetch('PATCH', `${CONFIG.TABLE_SC}/${shipmentId}`, {
      fields: { [CONFIG.FLD_TRACKING]: trackingNumbers.join('\n') },
    });

    return { ok: true };
  }

  // ─── 메인 실행 ───────────────────────────────────────────────────────
  async function run(statusEl) {
    const map = parseGrid();

    if (!map) {
      statusEl.textContent = '⚠️ TO번호/운송장번호가 있는 행을 찾을 수 없습니다. (콘솔 확인)';
      statusEl.style.color = 'orange';
      return;
    }

    const keys = Object.keys(map);
    statusEl.textContent = `처리 중... (0 / ${keys.length})`;
    statusEl.style.color = '#555';

    const results = [];
    for (let i = 0; i < keys.length; i++) {
      const to = keys[i];
      const trackings = map[to];
      statusEl.textContent = `처리 중... (${i + 1} / ${keys.length}) ${to}`;

      try {
        const res = await syncOne(to, trackings);
        results.push(res.ok
          ? `✓ ${to} → ${trackings.join(', ')}`
          : `✗ ${to} — ${res.reason}`
        );
      } catch (e) {
        console.error(`[TMS] ${to} 오류:`, e);
        results.push(`✗ ${to} — ${e.message}`);
      }
    }

    const allOk = results.every((r) => r.startsWith('✓'));
    statusEl.innerHTML = results.map((r) => `<div>${r}</div>`).join('');
    statusEl.style.color = allOk ? 'green' : '#c00';
  }

  // ─── 버튼 주입 ───────────────────────────────────────────────────────
  function inject() {
    if (document.getElementById(BTN_ID)) return;

    // 운송장번호 + 물품명 컬럼이 모두 있는 테이블 탐색
    let targetTable = null;
    for (const table of document.querySelectorAll('table')) {
      const text = table.innerText;
      if (text.includes('운송장번호') && text.includes('물품명')) {
        targetTable = table;
        break;
      }
    }
    if (!targetTable) return;

    const wrapper = document.createElement('div');
    wrapper.id = BTN_ID;
    wrapper.style.cssText = 'margin: 6px 0; display: flex; align-items: flex-start; gap: 12px; flex-wrap: wrap;';

    const btn = document.createElement('button');
    btn.textContent = 'TMS 운송장 전송';
    btn.style.cssText =
      'background: #1e6f9f; color: #fff; border: none; padding: 6px 16px; ' +
      'border-radius: 4px; cursor: pointer; font-size: 13px; white-space: nowrap;';

    const status = document.createElement('div');
    status.style.cssText = 'font-size: 12px; line-height: 1.6; padding-top: 4px;';

    btn.addEventListener('click', () => {
      btn.disabled = true;
      status.textContent = '';
      run(status).finally(() => { btn.disabled = false; });
    });

    wrapper.appendChild(btn);
    wrapper.appendChild(status);
    targetTable.parentNode.insertBefore(wrapper, targetTable);
    console.log('[TMS] 버튼 주입 완료');
  }

  // ─── MutationObserver로 동적 DOM 대기 ────────────────────────────────
  function waitAndInject() {
    inject();
    if (document.getElementById(BTN_ID)) return;

    const observer = new MutationObserver(() => {
      inject();
      if (document.getElementById(BTN_ID)) observer.disconnect();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => observer.disconnect(), 30000);
  }

  waitAndInject();
})();
