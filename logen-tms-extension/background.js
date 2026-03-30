// ─── 설정 ────────────────────────────────────────────────────────────
const CONFIG = {
  TOKEN: 'patU9ew1rwbJbEpOn.d5c7c1bb42c3ad69edd2701ee0424ddcb04c4d261a0ed422f8e5edaf1fa20edc',
  BASE: 'app4x70a8mOrIKsMf',
  TABLE_TO: 'tblfIEiPJaEF0DVoM',       // 배송요청 테이블
  FLD_TO_SHIPMENT: 'fld1rfeoDNQKASafk', // 배송요청.Shipment 링크 필드
  TABLE_SC: 'tbllg1JoHclGYer7m',       // Shipment 테이블
  FLD_TRACKING: 'fldv4U6Gx4d8BWPTb',   // Shipment.운송장번호 필드
};

// ─── Airtable fetch 헬퍼 ─────────────────────────────────────────────
async function atFetch(method, urlPath, body) {
  const res = await fetch(`https://api.airtable.com/v0/${CONFIG.BASE}/${urlPath}`, {
    method,
    headers: {
      Authorization: `Bearer ${CONFIG.TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Airtable ${res.status}: ${text}`);
  }
  return res.json();
}

// ─── TO번호 1건 처리 ─────────────────────────────────────────────────
async function syncOne(toNumber, trackingNumbers) {
  const encoded = encodeURIComponent(`FIND("${toNumber}", {logistics_PK})`);
  const toRes = await atFetch(
    'GET',
    `${CONFIG.TABLE_TO}?filterByFormula=${encoded}&fields[]=${CONFIG.FLD_TO_SHIPMENT}`
  );

  if (!toRes.records || toRes.records.length === 0) {
    return { ok: false, reason: 'TMS에서 배송요청 레코드를 찾을 수 없음' };
  }

  const shipmentLinks = toRes.records[0].fields[CONFIG.FLD_TO_SHIPMENT];
  if (!shipmentLinks || shipmentLinks.length === 0) {
    return { ok: false, reason: '배송요청에 연결된 Shipment 레코드 없음' };
  }

  await atFetch('PATCH', `${CONFIG.TABLE_SC}/${shipmentLinks[0]}`, {
    fields: { [CONFIG.FLD_TRACKING]: trackingNumbers.join('\n') },
  });

  return { ok: true };
}

// ─── 메시지 리스너 ───────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.action !== 'syncTracking') return false;

  const map = message.data; // { TO번호: [운송장번호, ...], ... }
  const keys = Object.keys(map);

  (async () => {
    const results = [];
    for (const toNumber of keys) {
      const trackings = map[toNumber];
      try {
        const res = await syncOne(toNumber, trackings);
        results.push(res.ok
          ? { ok: true, to: toNumber, trackings }
          : { ok: false, to: toNumber, reason: res.reason }
        );
      } catch (e) {
        results.push({ ok: false, to: toNumber, reason: e.message });
      }
    }
    sendResponse({ results });
  })();

  return true; // 비동기 sendResponse를 위해 true 반환
});
