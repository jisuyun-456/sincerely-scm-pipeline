import sys, json, re, csv
from datetime import date, timedelta
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

today = date(2026, 4, 7)
end_date = today + timedelta(days=14)

def parse_date(s):
    if not s:
        return None
    m = re.match(r'(\d+)/(\d+)', s.strip())
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    d = date(today.year, month, day)
    if (today - d).days > 60:
        d = date(today.year + 1, month, day)
    return d

def get_val(f, fid, default=''):
    v = f.get(fid, default)
    if isinstance(v, dict):
        return v.get('name', default)
    return v if v is not None else default

def parse_qty(v):
    try:
        return float(str(v).replace(',', '')) if v else 0.0
    except:
        return 0.0

def parse_parts(s):
    if not s:
        return ''
    return s.split(' || ')[0].strip()

# 그룹1 로드
with open(r'C:\Users\yjisu\.claude\projects\c--Users-yjisu-Desktop-SCM-WORK\5a3103be-820e-42d9-b348-7e50163ea78f\tool-results\mcp-claude_ai_Airtable-list_records_for_table-1775537401115.txt', encoding='utf-8') as f:
    g1_data = json.load(f)

g1_records = []
for r in g1_data['records']:
    fv = r['cellValuesByFieldId']
    date_str = get_val(fv, 'fldTS5N9aClRhFUSy')
    d = parse_date(date_str)
    if d is None or not (today <= d <= end_date):
        continue
    g1_records.append({
        'rec_id': r['id'],
        'movement_id': get_val(fv, 'fldOhFtJFBYsxxre7'),
        'parts': parse_parts(get_val(fv, 'fldQevLGnuqIuFRVO')),
        'project': get_val(fv, 'fldTiwebHjoUjrs5W'),
        'date_str': date_str,
        'date': d,
        'qty': parse_qty(get_val(fv, 'fld9JMFhIrTDzRzrD')),
        'stock': parse_qty(get_val(fv, 'fldd7yU3V7LEYuKk3')),
        'status': get_val(fv, 'fld8dqGaGuLHefQUs'),
    })

# 그룹2 데이터 (API 결과 하드코딩)
g2_raw = [
    {"id":"rec14Ee0hiLn69bdV","movement_id":"MM00205231","parts":"PT4696-킵세이프마그넷배터리2.0","status":"자재투입대기","stock":486,"qty":300},
    {"id":"rec15ugFhPqYnS0Dj","movement_id":"MM00205100","parts":"PT4696-킵세이프마그넷배터리2.0","status":"이동대기","stock":486,"qty":100},
    {"id":"rec2Yb6VQb3C1Uh4U","movement_id":"MM00205134","parts":"PT4886-챔피언피규어시상대세트(시상대)","status":"이동대기","stock":232,"qty":75},
    {"id":"rec3Wfe6vNTq3Shv5","movement_id":"MM00204024","parts":"PT5148-퀵차지도킹형보조배터리(type-C/C)_화이트","status":"자재투입대기","stock":684,"qty":0},
    {"id":"rec9HjwxXG8NCqQrt","movement_id":"MM00205427","parts":"PT3339-핸디링미니선풍기_화이트","status":"","stock":291,"qty":140},
    {"id":"recJFeUrU45JIVSMb","movement_id":"MM00204567","parts":"PT3900-리멤버탁상시계","status":"자재투입대기","stock":436,"qty":0},
    {"id":"recOyUceYLd4EGsJK","movement_id":"MM00189199","parts":"PT4954-챔피언피규어시상대세트(판넬)","status":"자재투입대기","stock":3714,"qty":0},
    {"id":"recPAChl7yqkEXg5j","movement_id":"MM00204569","parts":"PT3331-테크미니파우치","status":"자재투입대기","stock":580,"qty":0},
    {"id":"recYI3PvL7fyAbYxY","movement_id":"MM00205144","parts":"PT4954-챔피언피규어시상대세트(판넬)","status":"자재투입대기","stock":3714,"qty":75},
    {"id":"reccxjwJqfCWeG1XP","movement_id":"MM00204819","parts":"PT3365-와이드클립펜_올블랙","status":"자재투입대기","stock":583,"qty":300},
    {"id":"receM4QfFh2o6Hv7d","movement_id":"MM00204568","parts":"PT4757-마그넷케이블홀더_블랙","status":"이동대기","stock":167,"qty":0},
    {"id":"recynApxAfJsDdMDD","movement_id":"MM00205101","parts":"PT4400-라이트샤오미펜_화이트","status":"자재투입대기","stock":1129,"qty":100},
]

g2_records = [dict(r, rec_id=r['id'], project='', date_str='', date=None) for r in g2_raw]

def group_parts(records, sort_by_date=True):
    grouped = defaultdict(list)
    for r in records:
        grouped[r['parts']].append(r)
    result = []
    for parts, recs in grouped.items():
        total_qty = sum(r['qty'] for r in recs)
        stock = recs[0]['stock']
        replenish = max(0, total_qty - stock + 100)
        min_date = min((r['date'] for r in recs if r.get('date')), default=None)
        result.append({'parts': parts, 'recs': recs, 'total_qty': total_qty,
                       'stock': stock, 'replenish': replenish, 'min_date': min_date})
    if sort_by_date:
        result.sort(key=lambda x: x['min_date'] or date.max)
    else:
        result.sort(key=lambda x: -x['replenish'])
    return result

g1_grouped = group_parts(g1_records, sort_by_date=True)
g2_grouped = group_parts(g2_records, sort_by_date=False)
g1_need = sum(1 for g in g1_grouped if g['replenish'] > 0)
g2_need = sum(1 for g in g2_grouped if g['replenish'] > 0)

# ===== 출력 1: 텍스트 표 =====
print()
print('## 자재 투입 리스트 (4/7 ~ 4/21)')
print('조회: 임가공예정일 14일 이내 | 미완료 | 취소 제외')
print('생성: 2026-04-07 KST')
print()
print('---')
print()
print(f'### 조립투입 재고자재 — {len(g1_grouped)}개 파츠 / {len(g1_records)}건')
print()
for g in g1_grouped:
    print(f"**{g['parts']}** — {len(g['recs'])}건")
    print('| movement_id | 프로젝트 | 임가공예정일 | 발주요청수량 | 상태 |')
    print('|---|---|---|---|---|')
    for r in sorted(g['recs'], key=lambda x: x.get('date') or date.max):
        qty_str = f"{int(r['qty']):,}" if r['qty'] else '-'
        print(f"| {r['movement_id']} | {r.get('project') or '-'} | {r.get('date_str') or '-'} | {qty_str} | {r['status']} |")
    flag = 'X' if g['replenish'] > 0 else '-'
    print(f"-> 에이원재고: **{int(g['stock']):,}개** | 총 발주요청: **{int(g['total_qty']):,}개** | **보충수량: {int(g['replenish']):,}개** [{flag}]")
    print()

print('---')
print()
print(f'### 생산투입 (신시어리웨일즈) — {len(g2_grouped)}개 파츠 / {len(g2_records)}건')
print()
for g in g2_grouped:
    print(f"**{g['parts']}** — {len(g['recs'])}건")
    print('| movement_id | 발주요청수량 | 상태 |')
    print('|---|---|---|')
    for r in g['recs']:
        qty_str = f"{int(r['qty']):,}" if r['qty'] else '-'
        print(f"| {r['movement_id']} | {qty_str} | {r['status']} |")
    flag = 'X' if g['replenish'] > 0 else '-'
    print(f"-> 에이원재고: **{int(g['stock']):,}개** | 총 발주요청: **{int(g['total_qty']):,}개** | **보충수량: {int(g['replenish']):,}개** [{flag}]")
    print()

print('---')
print()
print('## 요약')
print(f'- 조립투입: {len(g1_grouped)}개 파츠, 보충필요 {g1_need}개 / 보충불필요 {len(g1_grouped)-g1_need}개')
print(f'- 생산투입: {len(g2_grouped)}개 파츠, 보충필요 {g2_need}개 / 보충불필요 {len(g2_grouped)-g2_need}개')
print(f'- **총 보충 필요 파츠: {g1_need + g2_need}개**')

# ===== 출력 2: CSV =====
csv_path = r'C:\Users\yjisu\Desktop\SCM_WORK\투입리스트_2026-04-07.csv'
with open(csv_path, 'w', newline='', encoding='utf-8-sig') as cf:
    writer = csv.writer(cf)
    writer.writerow(['그룹', '파츠명', 'movement_id', '프로젝트', '임가공예정일', '발주요청수량', '에이원재고', '보충수량', '상태'])
    for g in g1_grouped:
        for r in sorted(g['recs'], key=lambda x: x.get('date') or date.max):
            writer.writerow(['조립투입', g['parts'], r['movement_id'], r.get('project',''),
                             r.get('date_str',''), int(r['qty']) if r['qty'] else '',
                             int(g['stock']), int(g['replenish']), r['status']])
    writer.writerow([])
    for g in g2_grouped:
        for r in g['recs']:
            writer.writerow(['생산투입(신시어리웨일즈)', g['parts'], r['movement_id'], '',
                             '', int(r['qty']) if r['qty'] else '',
                             int(g['stock']), int(g['replenish']), r['status']])

print(f'\n[CSV 저장 완료] {csv_path}')
