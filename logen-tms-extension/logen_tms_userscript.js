// ==UserScript==
// @name         로젠 → TMS 운송장 자동 전송
// @namespace    sincerely-scm
// @version      1.6
// @description  로젠택배 그리드의 운송장번호를 Airtable TMS Shipment에 자동 업데이트 (3단계 매칭)
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

    // ① ② TO/PNA 매칭용 — 배송요청 테이블
    TABLE_TO:        'tblfIEiPJaEF0DVoM',
    FLD_TO_SHIPMENT: 'fld1rfeoDNQKASafk', // 배송요청.Shipment 링크

    // ③ fallback 매칭용 — Shipment 테이블 rollup 직접 조회
    TABLE_SC:        'tbllg1JoHclGYer7m',
    FLD_TRACKING:    'fldv4U6Gx4d8BWPTb', // 운송장번호 (저장 대상)
    FLD_SC_NAME:     'fldetwyTU2ZZ9YgDs', // 수령인
    FLD_SC_PHONE:    'fld7kFrMBiNDgptaw', // 수령인(연락처)
    FLD_SC_ADDR:     'fldyJHUh9gN44Ggnh', // 수령인(주소)
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
            reject(new Error('Airtable ' + res.status + ': ' + res.responseText));
          }
        },
        onerror: (err) => reject(new Error('네트워크 오류: ' + JSON.stringify(err))),
      });
    });
  }

  // ─── 전화번호 정규화 (숫자만) ────────────────────────────────────────
  function normalizePhone(phone) {
    return (phone || '').replace(/\D/g, '');
  }

  // ─── 그리드 파싱 ─────────────────────────────────────────────────────
  // 반환: [{ tracking, orderNo, pnaNo, name, phone, mobile, address }]
  function parseGrid() {
    const rows = [];

    for (const table of document.querySelectorAll('table')) {
      const headers = {};
      const theadCells = table.querySelectorAll('thead th, thead td');
      if (theadCells.length > 0) {
        theadCells.forEach((cell, idx) => { headers[cell.innerText.trim()] = idx; });
      } else {
        const firstRow = table.querySelector('tr');
        if (firstRow) {
          firstRow.querySelectorAll('th, td').forEach((cell, idx) => {
            headers[cell.innerText.trim()] = idx;
          });
        }
      }

      const tIdx = headers['운송장번호'];
      if (tIdx === undefined) continue;

      const itemIdx   = headers['물품명'];
      const nameIdx   = headers['수하인'];
      const phoneIdx  = headers['수하인전화'];
      const mobileIdx = headers['수하인휴대폰'];
      const addrIdx   = headers['수하인주소'];

      const bodyRows = table.querySelector('tbody')
        ? Array.from(table.querySelectorAll('tbody tr'))
        : Array.from(table.querySelectorAll('tr')).slice(1);

      for (const tr of bodyRows) {
        const tds = tr.querySelectorAll('td');
        if (tds.length <= tIdx) continue;

        const tracking = tds[tIdx].innerText.trim();
        if (!tracking || !/^\d{3}-\d{4}-\d{4}$/.test(tracking)) continue;

        const row = {
          tracking,
          orderNo: null,
          pnaNo:   null,
          name:    nameIdx   !== undefined ? (tds[nameIdx]?.innerText.trim()   || '') : '',
          phone:   phoneIdx  !== undefined ? (tds[phoneIdx]?.innerText.trim()  || '') : '',
          mobile:  mobileIdx !== undefined ? (tds[mobileIdx]?.innerText.trim() || '') : '',
          address: addrIdx   !== undefined ? (tds[addrIdx]?.innerText.trim()   || '') : '',
        };

        // 물품명에서 TO/MM/PNA 추출
        if (itemIdx !== undefined && tds[itemIdx]) {
          const item = tds[itemIdx].innerText.trim();
          if (/^(TO|MM)\d+/.test(item)) {
            row.orderNo = item.split('/')[0].trim();
          }
          const pnaMatch = item.match(/PNA(\d+)/i);
          if (pnaMatch) row.pnaNo = 'PNA' + pnaMatch[1];
        }

        rows.push(row);
      }

      if (rows.length > 0) break;
    }

    console.log('[TMS] parseGrid 결과:', rows);
    return rows.length > 0 ? rows : null;
  }

  // ─── 그룹핑 (TO/PNA 동일 = 같은 Shipment, 운송장 여러 개 묶음) ──────
  function groupRows(rows) {
    const groupMap = {};
    const groups   = [];

    for (const row of rows) {
      const key = row.orderNo || row.pnaNo
        || ('__fb__' + normalizePhone(row.mobile || row.phone) + '__' + row.tracking);

      if (!groupMap[key]) {
        groupMap[key] = {
          key,
          orderNo: row.orderNo,
          pnaNo:   row.pnaNo,
          name:    row.name,
          phone:   row.phone,
          mobile:  row.mobile,
          address: row.address,
          waybills: [],
        };
        groups.push(groupMap[key]);
      }
      const normalized = row.tracking.replace(/-/g, '');
      if (!groupMap[key].waybills.includes(normalized)) {
        groupMap[key].waybills.push(normalized);
      }
    }

    return groups;
  }

  // ─── ①② TO/PNA 매칭: 배송요청 경유 → Shipment ID 취득 ──────────────
  async function findShipmentByOrder(formula) {
    const encoded = encodeURIComponent(formula);
    const flds = [CONFIG.FLD_TO_SHIPMENT].map(f => 'fields[]=' + f).join('&');
    const res = await atFetch('GET', CONFIG.TABLE_TO + '?filterByFormula=' + encoded + '&' + flds);
    if (!res.records || res.records.length === 0) return null;

    const links = res.records[0].fields[CONFIG.FLD_TO_SHIPMENT];
    return links && links.length > 0 ? links[0] : null;
  }

  // ─── ③ fallback 매칭: Shipment 테이블 직접 조회 ──────────────────────
  // 수령인(연락처) 기준 검색 → 성함 크로스검증 → Shipment record ID 직접 반환
  async function findShipmentByContact(normPhone, rawPhone, name) {
    // 하이픈 있는 형식·숫자만 형식 모두 검색
    const formula = 'OR('
      + 'FIND("' + normPhone + '",SUBSTITUTE({수령인(연락처)},"-","")),'
      + 'FIND("' + rawPhone  + '",{수령인(연락처)})'
      + ')';
    const encoded = encodeURIComponent(formula);
    const flds = [CONFIG.FLD_SC_NAME, CONFIG.FLD_SC_PHONE]
      .map(f => 'fields[]=' + f).join('&');

    const res = await atFetch('GET', CONFIG.TABLE_SC + '?filterByFormula=' + encoded + '&' + flds);
    console.log('[TMS] 연락처 fallback 결과:', res);

    if (!res.records || res.records.length === 0) return null;

    let matched = res.records[0];

    // 복수 결과 시 수령인 성함 크로스검증
    if (name && res.records.length > 1) {
      const normName = name.replace(/\s/g, '');
      const byName = res.records.find(r => {
        const aName = (r.fields[CONFIG.FLD_SC_NAME] || '').replace(/\s/g, '');
        return aName === normName || aName.includes(normName) || normName.includes(aName);
      });
      if (byName) matched = byName;
    }

    return matched.id; // Shipment record ID 직접 반환
  }

  // ─── 3단계 매칭 + 운송장 저장 ────────────────────────────────────────
  async function syncGroup(group) {
    let shipmentId = null;
    let matchType  = '';

    // ① TO/MM번호 매칭
    if (group.orderNo) {
      shipmentId = await findShipmentByOrder('FIND("' + group.orderNo + '",{logistics_PK})');
      if (shipmentId) matchType = 'TO:' + group.orderNo;
    }

    // ② PNA번호 매칭
    if (!shipmentId && group.pnaNo) {
      shipmentId = await findShipmentByOrder('FIND("' + group.pnaNo + '",{logistics_PK})');
      if (shipmentId) matchType = 'PNA:' + group.pnaNo;
    }

    // ③ 연락처 fallback — Shipment 테이블 직접 조회
    if (!shipmentId) {
      const rawPhone  = group.mobile || group.phone;
      const normPhone = normalizePhone(rawPhone);

      if (normPhone.length >= 9) {
        shipmentId = await findShipmentByContact(normPhone, rawPhone, group.name);
        if (shipmentId) matchType = '연락처:' + normPhone + '+성함:' + group.name;
      }
    }

    if (!shipmentId) {
      return {
        ok: false,
        reason: 'TO/PNA 없음, 연락처(' + (group.phone || group.mobile) + ') 매칭 실패',
      };
    }

    // 운송장번호 저장
    await atFetch('PATCH', CONFIG.TABLE_SC + '/' + shipmentId, {
      fields: { [CONFIG.FLD_TRACKING]: group.waybills.join('\n') },
    });

    return { ok: true, matchType };
  }

  // ─── 결과 라인을 DOM으로 추가 (innerHTML 미사용) ─────────────────────
  function appendResult(container, text) {
    const div = document.createElement('div');
    div.textContent = text;
    container.appendChild(div);
  }

  // ─── 메인 실행 ───────────────────────────────────────────────────────
  async function run(statusEl) {
    const rows = parseGrid();
    if (!rows) {
      statusEl.textContent = '⚠️ 운송장번호가 있는 행을 찾을 수 없습니다. (콘솔 확인)';
      statusEl.style.color = 'orange';
      return;
    }

    const groups = groupRows(rows);
    statusEl.textContent = '처리 중... (0 / ' + groups.length + ')';
    statusEl.style.color = '#555';

    const results = [];
    for (let i = 0; i < groups.length; i++) {
      const g = groups[i];
      const label = g.orderNo || g.pnaNo || g.name || g.phone || g.mobile || '?';
      statusEl.textContent = '처리 중... (' + (i + 1) + ' / ' + groups.length + ') ' + label;

      try {
        const res = await syncGroup(g);
        results.push(res.ok
          ? '✓ ' + label + ' [' + res.matchType + '] → ' + g.waybills.join(', ')
          : '✗ ' + label + ' — ' + res.reason
        );
      } catch (e) {
        console.error('[TMS] ' + label + ' 오류:', e);
        results.push('✗ ' + label + ' — ' + e.message);
      }
    }

    // 결과 표시 (DOM 직접 생성, innerHTML 미사용)
    while (statusEl.firstChild) statusEl.removeChild(statusEl.firstChild);
    const allOk = results.every(r => r.startsWith('✓'));
    statusEl.style.color = allOk ? 'green' : '#c00';
    for (const r of results) appendResult(statusEl, r);
  }

  // ─── 버튼 주입 ───────────────────────────────────────────────────────
  function inject() {
    if (document.getElementById(BTN_ID)) return;

    let targetTable = null;
    for (const table of document.querySelectorAll('table')) {
      if (table.innerText.includes('운송장번호')) {
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

  // ─── MutationObserver로 동적 DOM 감시 (영구) ─────────────────────────
  // 조회(F2) 클릭 시 테이블 DOM이 교체되어 버튼이 사라지므로
  // observer를 disconnect하지 않고 계속 감시 → 버튼 없으면 재주입
  function waitAndInject() {
    inject();

    const observer = new MutationObserver(() => {
      if (!document.getElementById(BTN_ID)) {
        inject();
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    // 타임아웃 제거 — 페이지가 살아있는 동안 계속 감시
  }

  waitAndInject();
})();
