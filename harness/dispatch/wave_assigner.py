"""Stage B+C+D — Wave 배정 알고리즘 (Sub-Spec 3).

Pipeline:
1. Override 처리: wave_locked=True 분리 (Stage D, 다음 cycle skip)
2. Autonomy filter: autonomous 제외, locked-in 강제 라벨 (Stage C 보조)
3. NULL slot → '수동' wave 분리
4. Stage B Greedy bin-packing: (slot, region) 그룹 + PNA cluster + Best-Fit Decreasing
5. Stage B' SA local search: swap/move 무작위 시도 + Metropolis 수락 (P3.5 Decision 4)
6. Stage C Spillover: capacity 부족 → spillover_로젠 (지방) / spillover_고고엑스 (peak 시즌·소형)

Tier → 후보 wave 매핑 (P3.5 Decision 1: 인천=모두 가능 / Decision 3: tier2=W1→W2→W3):
- tier1_seoul: [W1, W2, W3]
- tier2_이장훈_gyeonggi: [W1, W2, W3]
- tier3_gyeonggi_etc: [W2, W3]
- tier4_incheon: [W1, W2, W3]
- tier5_provincial: [W3]
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional


DRIVER_LIMITS: Dict[str, Dict] = {
    'W1': {'driver_id': 'CA-0002', 'name': '이장훈', 'max_cbm': 4.5, 'max_count': 3,
           'regions': frozenset({'tier1_seoul', 'tier2_이장훈_gyeonggi', 'tier4_incheon'}),
           'preferred_slots': frozenset({'오전'}),
           'pattern': '09:00_고정'},
    'W2': {'driver_id': 'CA-NEW-1', 'name': '조희선', 'max_cbm': 7.616, 'max_count': 6,
           'regions': frozenset({'tier1_seoul', 'tier2_이장훈_gyeonggi', 'tier3_gyeonggi_etc', 'tier4_incheon'}),
           'preferred_slots': frozenset({'무관', '오전', '오후 1 (오후 2시 - 4시)', '오후 2 (오후 4시 - 6시)'}),
           'pattern': '1회_99%_고정'},
    'W3': {'driver_id': 'CA-0003', 'name': '박종성', 'max_cbm': 9.486, 'max_count': 8,
           'regions': frozenset({'tier1_seoul', 'tier2_이장훈_gyeonggi', 'tier3_gyeonggi_etc',
                                 'tier4_incheon', 'tier5_provincial'}),
           'preferred_slots': frozenset({'무관', '오전', '오후 1 (오후 2시 - 4시)', '오후 2 (오후 4시 - 6시)'}),
           'pattern': 'trigger_기반'},
}

TIER_TO_CANDIDATES: Dict[str, List[str]] = {
    'tier1_seoul':           ['W1', 'W2', 'W3'],
    'tier2_이장훈_gyeonggi':  ['W1', 'W2', 'W3'],
    'tier3_gyeonggi_etc':    ['W2', 'W3'],
    'tier4_incheon':         ['W1', 'W2', 'W3'],
    'tier5_provincial':      ['W3'],
    'unknown':               [],
}

WAVE_IDS = ('W1', 'W2', 'W3', 'spillover_고고엑스', 'spillover_로젠', 'locked-in', '수동')

# 자동배차 신뢰도 floor (P1 Task 1.7): slot_confidence * cbm_confidence < floor → '수동'.
# 결정론 CBM(conf 1.0) shipment만 자동 점등, 저신뢰(퍼지·기본값)는 사용자 검토.
CONFIDENCE_FLOOR = 0.8

# ── LEVER2 (2026-06-23, opt-in) — 부분매칭 conf 0.7 CBM 활용 ───────────────────
# 부분매칭 deterministic CBM 은 매칭된 라인만 합산 = 과소추정 → 그대로 자동배차하면 차량 과적
# 위험. 'separate' 모드는 slot/cbm 신뢰도를 분리 게이트하고, 용량 검사에서 저신뢰 CBM 을
# effective_cbm = cbm/cbm_conf 로 인플레이트해 과소추정이 과적으로 이어지지 않게 한다.
# 기본 'product' = 현행(곱 floor, 무변경). 운영 승인 후 'separate' 로 전환.
CONF_GATE_MODE = 'product'    # 'product'(현행) | 'separate'(LEVER2 활성)
SLOT_FLOOR = 0.8              # separate 모드: 슬롯 신뢰도 하한
CBM_FLOOR = 0.7              # separate 모드: CBM 신뢰도 하한 (부분매칭 0.7 허용)
CAPACITY_MARGIN_CAP = 1.6    # effective_cbm 인플레이션 상한 (과도한 spillover 방지)


def _below_floor(s: 'Shipment', confidence_floor: float) -> bool:
    """저신뢰 → 수동 분리 여부. product=곱 floor(현행) / separate=slot·cbm 분리 게이트(LEVER2)."""
    if CONF_GATE_MODE == 'separate':
        return s.slot_confidence < SLOT_FLOOR or s.cbm_confidence < CBM_FLOOR
    return s.slot_confidence * s.cbm_confidence < confidence_floor


def _effective_cbm(s: 'Shipment') -> float:
    """용량 검사용 CBM. separate 모드에서 저신뢰(부분매칭) CBM 을 인플레이트해 과적 방지."""
    if CONF_GATE_MODE == 'separate' and 0.0 < s.cbm_confidence < 1.0:
        return min(s.cbm / s.cbm_confidence, s.cbm * CAPACITY_MARGIN_CAP)
    return s.cbm


QUICK_METHODS = frozenset({
    '퀵(수도권)', '퀵(지방)', '자체기사',
    '바로고', '고객직접퀵배차', '신시어리퀵',
})
# 외부 퀵 운송(고고엑스 등) — '자체기사'는 제외(W1/W2/W3 본인이 자체기사). min-load 시 자체기사
# 트럭으로 끌어오면 SLA·운송수단이 맞지 않는 대상.
EXTERNAL_QUICK_METHODS = QUICK_METHODS - frozenset({'자체기사'})


@dataclass
class Shipment:
    id: str
    project_code: str
    slot: Optional[str]
    region: str
    cbm: float
    cbm_confidence: float = 0.7
    slot_confidence: float = 0.8
    assigned_partner: Optional[str] = None
    wave_locked: bool = False
    method: Optional[str] = None


@dataclass
class WavePlan:
    wave_id: str
    shipments: List[Shipment] = field(default_factory=list)

    @property
    def total_cbm(self) -> float:
        return sum(s.cbm for s in self.shipments)

    @property
    def count(self) -> int:
        return len(self.shipments)


def _empty_plans() -> Dict[str, WavePlan]:
    return {wid: WavePlan(wid) for wid in WAVE_IDS}


def _seasonal_mode(today_iso: str) -> str:
    month = int(today_iso[5:7])
    return 'peak' if month in {11, 12, 1, 2} else 'off-peak'


def _can_fit(wave_id: str, additional_cbm: float, additional_count: int, plan: WavePlan) -> bool:
    if wave_id not in DRIVER_LIMITS:
        return True
    limits = DRIVER_LIMITS[wave_id]
    return (plan.total_cbm + additional_cbm <= limits['max_cbm']
            and plan.count + additional_count <= limits['max_count'])


def _region_ok(wave_id: str, region: str) -> bool:
    if wave_id not in DRIVER_LIMITS:
        return True
    return region in DRIVER_LIMITS[wave_id]['regions']


def _slot_ok(wave_id: str, slot: Optional[str]) -> bool:
    """shipment 슬롯이 해당 기사 preferred_slots 내에 있는지 확인. 무관/None 슬롯 → 모두 허용."""
    if not slot or slot == '무관':
        return True
    if wave_id not in DRIVER_LIMITS:
        return True
    return slot in DRIVER_LIMITS[wave_id]['preferred_slots']


def _spillover_target(region: str, group_cbms: List[float], mode: str,
                      method: Optional[str] = None) -> str:
    if method in QUICK_METHODS:
        return 'spillover_고고엑스'
    # 성수기 소형(≤0.5 CBM) 화물은 고고엑스(택배 대체) — P3.5 문서 룰 활성화
    # (기존엔 mode/group_cbms 가 무시돼 전부 로젠으로 갔음). (2026-06-23)
    if mode == 'peak' and group_cbms and max(group_cbms) <= 0.5:
        return 'spillover_고고엑스'
    return 'spillover_로젠'


def _split_by_autonomy(shipments: List[Shipment], partner_autonomy: Dict[str, str],
                      plans: Dict[str, WavePlan]) -> List[Shipment]:
    """autonomous → 제외, locked-in → 'locked-in' wave. Input Shipment 비변경 (idempotent)."""
    remaining = []
    for s in shipments:
        autonomy = partner_autonomy.get(s.assigned_partner or '', 'unknown') if s.assigned_partner else 'unknown'
        if autonomy == 'autonomous':
            continue
        if autonomy == 'locked-in':
            plans['locked-in'].shipments.append(s)
            continue
        remaining.append(s)
    return remaining


def assign_waves_greedy(shipments: List[Shipment], partner_autonomy: Dict[str, str],
                        today_iso: str, confidence_floor: float = 0.0) -> Dict[str, WavePlan]:
    """Best-Fit Decreasing per (slot, region) group + PNA cluster.

    confidence_floor>0 (프로덕션): slot_confidence*cbm_confidence < floor 인 shipment를
    자동배차 전에 '수동'으로 분리 (P1 Task 1.7). 기본 0.0 = 미적용(단위테스트·baseline용).
    """
    plans = _empty_plans()

    # Stage D: override
    locked_now = [s for s in shipments if s.wave_locked]
    active = [s for s in shipments if not s.wave_locked]
    for s in locked_now:
        plans['수동'].shipments.append(s)  # 사용자 검토 대상

    # Stage C 보조: autonomy filter
    active = _split_by_autonomy(active, partner_autonomy, plans)

    # 신뢰도 floor → 수동 (P1 Task 1.7): BFD 배차 진입 전 저신뢰 shipment 분리.
    # floor>0(프로덕션)일 때만 적용 — 자동배차는 고신뢰(결정론 CBM)만 점등.
    if confidence_floor > 0:
        confident = []
        for s in active:
            if _below_floor(s, confidence_floor):
                plans['수동'].shipments.append(s)  # 사용자 검토 대상
            else:
                confident.append(s)
        active = confident

    # NULL slot → 수동
    active_with_slot = []
    for s in active:
        if s.slot is None:
            plans['수동'].shipments.append(s)
        else:
            active_with_slot.append(s)

    # Stage B: group by (slot, region) + PNA cluster + BFD
    mode = _seasonal_mode(today_iso)
    by_key: Dict[tuple, List[Shipment]] = defaultdict(list)
    for s in active_with_slot:
        by_key[(s.slot, s.region)].append(s)

    # Order groups by total cbm desc (큰 그룹 먼저)
    sorted_keys = sorted(by_key.keys(), key=lambda k: -sum(s.cbm for s in by_key[k]))

    for (slot, region) in sorted_keys:
        group = by_key[(slot, region)]
        # PNA cluster: 같은 project_code끼리 묶음 + cbm 내림차순
        group.sort(key=lambda s: (s.project_code, -s.cbm))

        candidates = TIER_TO_CANDIDATES.get(region, [])
        candidates = [c for c in candidates if _slot_ok(c, slot)]

        # Best-Fit Decreasing: shipment 하나씩 → 잔여 capacity 가장 작은 wave
        for ship in group:
            best_wave = None
            best_residual = math.inf
            eff_cbm = _effective_cbm(ship)  # separate 모드: 저신뢰 CBM 인플레이트(과적 방지)
            for wid in candidates:
                if not _region_ok(wid, region):
                    continue
                if not _can_fit(wid, eff_cbm, 1, plans[wid]):
                    continue
                limits = DRIVER_LIMITS[wid]
                residual = limits['max_cbm'] - (plans[wid].total_cbm + eff_cbm)
                if residual < best_residual:
                    best_residual = residual
                    best_wave = wid
            if best_wave:
                plans[best_wave].shipments.append(ship)
            elif ship.cbm > DRIVER_LIMITS['W3']['max_cbm']:
                # 단건 CBM이 최대 기사 한도 초과 → 용차/특수배송 필요, 수동 분류
                plans['수동'].shipments.append(ship)
            else:
                target = _spillover_target(region, [ship.cbm], mode, ship.method)
                plans[target].shipments.append(ship)

    return plans


# ============================================================
# Stage B' — SA Local Search (P3.5 Decision 4)
# ============================================================

CAPACITY_VIOLATION_PENALTY = 100.0
REGION_VIOLATION_PENALTY = 50.0


def _score(plans: Dict[str, WavePlan]) -> float:
    """Higher is better. Sum of utilization - violation penalties."""
    score = 0.0
    for wid, plan in plans.items():
        if wid in DRIVER_LIMITS:
            limits = DRIVER_LIMITS[wid]
            util = plan.total_cbm / limits['max_cbm']
            score += util
            if plan.total_cbm > limits['max_cbm']:
                score -= CAPACITY_VIOLATION_PENALTY
            if plan.count > limits['max_count']:
                score -= CAPACITY_VIOLATION_PENALTY
            for s in plan.shipments:
                if not _region_ok(wid, s.region):
                    score -= REGION_VIOLATION_PENALTY
                if not _slot_ok(wid, s.slot):
                    score -= REGION_VIOLATION_PENALTY
    return score


def _clone(plans: Dict[str, WavePlan]) -> Dict[str, WavePlan]:
    return {wid: WavePlan(wid, list(p.shipments)) for wid, p in plans.items()}


SOURCE_WAVES = ('W1', 'W2', 'W3', 'spillover_로젠')
TARGET_WAVES = ('W1', 'W2', 'W3', 'spillover_로젠')


def _neighbor(plans: Dict[str, WavePlan], rng: random.Random) -> Optional[Dict[str, WavePlan]]:
    """무작위 swap 또는 move. spillover_로젠 ↔ W1/W2/W3 양방향 허용 (capacity 회수)."""
    eligible_waves = [wid for wid in SOURCE_WAVES if plans[wid].count > 0]
    if not eligible_waves:
        return None

    new_plans = _clone(plans)
    op = rng.choice(['swap', 'move'])

    if op == 'swap' and len(eligible_waves) >= 2:
        w_a, w_b = rng.sample(eligible_waves, 2)
        if not new_plans[w_a].shipments or not new_plans[w_b].shipments:
            return None
        i = rng.randrange(len(new_plans[w_a].shipments))
        j = rng.randrange(len(new_plans[w_b].shipments))
        s_a = new_plans[w_a].shipments[i]
        s_b = new_plans[w_b].shipments[j]
        new_plans[w_a].shipments[i] = s_b
        new_plans[w_b].shipments[j] = s_a
        return new_plans

    # move
    w_from = rng.choice(eligible_waves)
    targets = [w for w in TARGET_WAVES if w != w_from]
    w_to = rng.choice(targets)
    if not new_plans[w_from].shipments:
        return None
    i = rng.randrange(len(new_plans[w_from].shipments))
    ship = new_plans[w_from].shipments.pop(i)
    new_plans[w_to].shipments.append(ship)
    return new_plans


def refine_with_sa(plans: Dict[str, WavePlan], *, max_iter: int = 500,
                   t_initial: float = 100.0, alpha: float = 0.95,
                   seed: int = 42) -> Dict[str, WavePlan]:
    """Simulated Annealing local search. Deterministic via seed."""
    rng = random.Random(seed)
    current = _clone(plans)
    best = _clone(plans)
    current_score = _score(current)
    best_score = current_score
    t = t_initial

    for _ in range(max_iter):
        if t < 0.01:
            break
        candidate = _neighbor(current, rng)
        if candidate is None:
            t *= alpha
            continue
        cand_score = _score(candidate)
        delta = cand_score - current_score
        if delta > 0 or rng.random() < math.exp(delta / t):
            current = candidate
            current_score = cand_score
            if current_score > best_score:
                best = _clone(current)
                best_score = current_score
        t *= alpha

    return best


def _ensure_minimum_load(plans: Dict[str, WavePlan]) -> Dict[str, WavePlan]:
    """W1(이장훈)·W2(조희선) 영업일 최소 1건 보장.

    active shipments ≥ 2건일 때 W1·W2 중 0건인 wave가 있으면
    donor(W3 → spillover_로젠 → spillover_고고엑스)에서 적합한 건을 이동.
    W1은 slot='오전' + 호환 region 조건 준수, W2는 region만 확인.
    """
    active_total = sum(
        plans[w].count for w in ("W1", "W2", "W3", "spillover_로젠", "spillover_고고엑스")
    )
    if active_total < 2:
        return plans

    donor_priority = ("W3", "spillover_로젠", "spillover_고고엑스")

    for gw in ("W1", "W2"):
        if plans[gw].count > 0:
            continue
        for donor in donor_priority:
            if plans[donor].count == 0:
                continue
            for i, ship in enumerate(plans[donor].shipments):
                # 외부 퀵(고고엑스 등) 배송을 자체기사 트럭(W1/W2)으로 끌어오지 않음 — 운송수단 보존.
                # ('자체기사' 화물의 W3→W1 재배치는 정상 허용). (2026-06-23)
                if ship.method in EXTERNAL_QUICK_METHODS:
                    continue
                if not _region_ok(gw, ship.region):
                    continue
                if not _can_fit(gw, ship.cbm, 1, plans[gw]):
                    continue
                if not _slot_ok(gw, ship.slot):
                    continue
                plans[donor].shipments.pop(i)
                plans[gw].shipments.append(ship)
                break
            if plans[gw].count > 0:
                break

    return plans


def assign_waves(shipments: List[Shipment], partner_autonomy: Dict[str, str],
                today_iso: str, *, use_sa: bool = True,
                sa_iter: int = 500, sa_seed: int = 42,
                confidence_floor: float = 0.0) -> Dict[str, WavePlan]:
    """메인 entry — Greedy → (optional) SA refinement → minimum load 보장.

    Args:
        use_sa: False 면 Greedy 결과만 반환 (smoke test·baseline 비교용)
        confidence_floor: >0 이면 저신뢰 shipment 자동배차 제외(수동). 프로덕션은 CONFIDENCE_FLOOR.
    """
    plans = assign_waves_greedy(shipments, partner_autonomy, today_iso,
                                confidence_floor=confidence_floor)
    if use_sa:
        plans = refine_with_sa(plans, max_iter=sa_iter, seed=sa_seed)
    plans = _ensure_minimum_load(plans)
    return plans


def compute_utilization(plans: Dict[str, WavePlan]) -> Dict[str, float]:
    """진단용: W1·W2·W3 적재율."""
    return {
        wid: (plans[wid].total_cbm / DRIVER_LIMITS[wid]['max_cbm']) if wid in DRIVER_LIMITS else 0.0
        for wid in ('W1', 'W2', 'W3')
    }
