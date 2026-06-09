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
           'preferred_slots': frozenset({'무관', '오전', '오후 1 (오후 2시 - 4시)'}),
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


QUICK_METHODS = frozenset({
    '퀵(수도권)', '퀵(지방)', '자체기사',
    '바로고', '고객직접퀵배차', '신시어리퀵',
})


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


def _slot_filter_w1(candidates: List[str], slot: Optional[str]) -> List[str]:
    """W1 이장훈은 오전/무관 슬롯만 적재. 무관은 오전 시간대 포함이므로 허용."""
    if 'W1' in candidates and slot not in ('오전', '무관', None):
        return [c for c in candidates if c != 'W1']
    return candidates


def _spillover_target(region: str, group_cbms: List[float], mode: str,
                      method: Optional[str] = None) -> str:
    if method in QUICK_METHODS:
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
                        today_iso: str) -> Dict[str, WavePlan]:
    """Best-Fit Decreasing per (slot, region) group + PNA cluster."""
    plans = _empty_plans()

    # Stage D: override
    locked_now = [s for s in shipments if s.wave_locked]
    active = [s for s in shipments if not s.wave_locked]
    for s in locked_now:
        plans['수동'].shipments.append(s)  # 사용자 검토 대상

    # Stage C 보조: autonomy filter
    active = _split_by_autonomy(active, partner_autonomy, plans)

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
        candidates = _slot_filter_w1(candidates, slot)

        # Best-Fit Decreasing: shipment 하나씩 → 잔여 capacity 가장 작은 wave
        for ship in group:
            best_wave = None
            best_residual = math.inf
            for wid in candidates:
                if not _region_ok(wid, region):
                    continue
                if not _can_fit(wid, ship.cbm, 1, plans[wid]):
                    continue
                limits = DRIVER_LIMITS[wid]
                residual = limits['max_cbm'] - (plans[wid].total_cbm + ship.cbm)
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
                if wid == 'W1' and s.slot not in ('오전', '무관', None):
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
                if not _region_ok(gw, ship.region):
                    continue
                if not _can_fit(gw, ship.cbm, 1, plans[gw]):
                    continue
                if gw == "W1" and ship.slot not in ("오전", "무관", None):
                    continue
                plans[donor].shipments.pop(i)
                plans[gw].shipments.append(ship)
                break
            if plans[gw].count > 0:
                break

    return plans


def assign_waves(shipments: List[Shipment], partner_autonomy: Dict[str, str],
                today_iso: str, *, use_sa: bool = True,
                sa_iter: int = 500, sa_seed: int = 42) -> Dict[str, WavePlan]:
    """메인 entry — Greedy → (optional) SA refinement → minimum load 보장.

    Args:
        use_sa: False 면 Greedy 결과만 반환 (smoke test·baseline 비교용)
    """
    plans = assign_waves_greedy(shipments, partner_autonomy, today_iso)
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
