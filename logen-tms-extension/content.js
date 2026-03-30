(function () {
  'use strict';

  const BTN_ID = 'tms-tracking-btn-wrapper';

  // ─── 그리드 파싱 ────────────────────────────────────────────────────
  function parseGrid() {
    const map = {};

    for (const table of document.querySelectorAll('table')) {
      let trackingIdx = -1;
      let itemIdx = -1;

      // 1) thead 안의 셀 먼저 탐색
      const theadCells = table.querySelectorAll('thead th, thead td');
      if (theadCells.length > 0) {
        theadCells.forEach((cell, idx) => {
          const text = cell.innerText.trim();
          if (text === '운송장번호') trackingIdx = idx;
          if (text === '물품명') itemIdx = idx;
        });
      }

      // 2) thead 없으면 첫 번째 tr로 fallback
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

      // 3) 데이터 행 수집
      const bodyRows = table.querySelector('tbody')
        ? Array.from(table.querySelectorAll('tbody tr'))
        : Array.from(table.querySelectorAll('tr')).slice(1);

      for (const tr of bodyRows) {
        const tds = tr.querySelectorAll('td');
        if (tds.length <= Math.max(trackingIdx, itemIdx)) continue;

        const tracking = tds[trackingIdx].innerText.trim();
        const itemName = tds[itemIdx].innerText.trim();

        if (!tracking || !/^\d{3}-\d{4}-\d{4}$/.test(tracking)) continue;
        if (!itemName.startsWith('TO') || !itemName.includes('/')) continue;

        const toNumber = itemName.split('/')[0].trim();
        if (!map[toNumber]) map[toNumber] = [];
        if (!map[toNumber].includes(tracking)) map[toNumber].push(tracking);
      }

      if (Object.keys(map).length > 0) break;
    }

    return Object.keys(map).length > 0 ? map : null;
  }

  // ─── 메인 실행 ───────────────────────────────────────────────────────
  async function run(statusEl) {
    const map = parseGrid();

    if (!map) {
      statusEl.textContent = '⚠️ TO번호/운송장번호가 있는 행을 찾을 수 없습니다.';
      statusEl.style.color = 'orange';
      return;
    }

    const keys = Object.keys(map);
    statusEl.textContent = `처리 중... (0 / ${keys.length})`;
    statusEl.style.color = '#555';

    // background service worker에 Airtable 작업 위임
    chrome.runtime.sendMessage(
      { action: 'syncTracking', data: map },
      (response) => {
        if (!response) {
          statusEl.textContent = '✗ 확장프로그램 오류 (background 응답 없음)';
          statusEl.style.color = '#c00';
          return;
        }

        const lines = response.results.map((r) =>
          r.ok
            ? `✓ ${r.to} → ${r.trackings.join(', ')}`
            : `✗ ${r.to} — ${r.reason}`
        );
        const allOk = response.results.every((r) => r.ok);
        statusEl.innerHTML = lines.map((l) => `<div>${l}</div>`).join('');
        statusEl.style.color = allOk ? 'green' : '#c00';
      }
    );
  }

  // ─── 버튼 주입 ───────────────────────────────────────────────────────
  function inject() {
    if (document.getElementById(BTN_ID)) return;

    let targetTable = null;
    for (const table of document.querySelectorAll('table')) {
      if (table.innerText.includes('운송장번호') && table.innerText.includes('물품명')) {
        targetTable = table;
        break;
      }
    }
    if (!targetTable) return;

    const wrapper = document.createElement('div');
    wrapper.id = BTN_ID;
    wrapper.style.cssText =
      'margin: 6px 0; display: flex; align-items: flex-start; gap: 12px; flex-wrap: wrap;';

    const btn = document.createElement('button');
    btn.textContent = 'TMS 운송장 전송';
    btn.style.cssText =
      'background: #1e6f9f; color: #fff; border: none; padding: 6px 16px; ' +
      'border-radius: 4px; cursor: pointer; font-size: 13px; white-space: nowrap;';

    const status = document.createElement('div');
    status.style.cssText = 'font-size: 12px; line-height: 1.6; padding-top: 4px;';

    btn.addEventListener('click', () => {
      btn.disabled = true;
      status.textContent = '처리 중...';
      status.style.color = '#555';
      run(status).finally(() => { btn.disabled = false; });
    });

    wrapper.appendChild(btn);
    wrapper.appendChild(status);
    targetTable.parentNode.insertBefore(wrapper, targetTable);
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
