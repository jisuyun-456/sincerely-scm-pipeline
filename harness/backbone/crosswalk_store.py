"""굿즈명↔견적코드 결정론 크로스워크 로더 (git-SSOT).

spec: docs/superpowers/specs/2026-08-12-bridge-cbm-crosswalk-design.md §4.2~4.3

SSOT = data/crosswalk/goods_crosswalk.csv (git 추적). 크로스워크는 **신원 매핑만**
보유하며 CBM 값을 저장하지 않는다 — CBM SSOT는 TMS Product다.

검증상태='확정' ∧ 키유형='굿즈명' 행만 결정론 맵에 적재한다. 같은 정규화 키에
서로 다른 견적코드를 가진 확정 행이 있으면 조용히 last-wins 하지 않는다.

런타임(`load_crosswalk`)과 검증(`validate_crosswalk`)은 분리되어 있다(§4.2 2026-08-12 개정):
런타임은 충돌 키를 양쪽 다 제외 + 경고만 하고 raise하지 않는다(라인당 호출·핫루프이므로).
검증은 같은 충돌을 loud하게 raise한다 — 사람이 파일을 고치는 시점에만.
"""
from __future__ import annotations

import csv
import logging
import os
import re

logger = logging.getLogger(__name__)

# 리포 루트 기준 기본 경로 (harness/backbone/ 에서 두 단계 위)
CROSSWALK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "crosswalk", "goods_crosswalk.csv",
)

STATUS_CONFIRMED = "확정"
KEYTYPE_GOODS = "굿즈명"

_cache_store: dict[str, dict[str, str]] = {}


class CrosswalkConflictError(Exception):
    """같은 정규화 키에 서로 다른 견적코드를 가진 확정 행이 둘 이상."""


def crosswalk_key(raw: str) -> str:
    """조회 키 — 공백 제거 + casefold. 괄호·[n]·_접미를 보존한다.

    normalize_goods 를 쓰지 않는 것이 의도다: '(S)'·'(M)'·'(무릎담요)' 같은 괄호가
    SKU 구분자이며, 제거하면 서로 다른 제품이 한 키로 뭉개진다(실측 충돌 27건).
    """
    return re.sub(r"\s+", "", raw or "").casefold()


def clear_cache() -> None:
    _cache_store.clear()


def _iter_confirmed_goods_rows(p: str):
    """확정·굿즈명 행을 (정규화키, 견적코드upper, 표준키raw) 튜플로 yield. 파일 없으면 빈 이터레이터."""
    if not os.path.exists(p):
        return
    with open(p, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if (row.get("검증상태") or "").strip() != STATUS_CONFIRMED:
                continue
            if (row.get("키유형") or "").strip() != KEYTYPE_GOODS:
                continue
            raw = (row.get("표준키") or "").strip()
            code = (row.get("TMS_견적코드") or "").strip().upper()
            if not raw or not code:
                continue
            key = crosswalk_key(raw)
            if not key:
                continue
            yield key, code, raw


def load_crosswalk(path: str | None = None, *, _cache: bool = True) -> dict[str, str]:
    """정규화키 → 견적코드(upper). 확정·굿즈명 행만. 파일 없으면 {}.

    파일 부재를 정상으로 취급하는 것은 의도적이다 — 크로스워크 미배포 환경에서
    1.5단이 자동 무력화되고 기존 1~4단 동작이 그대로 유지된다(spec §4.3, §10).

    충돌(같은 정규화 키에 다른 확정 견적코드) 발생 시 그 키를 결정론 맵에서 **양쪽 다 제외**하고
    경고 로그만 남긴다 — raise하지 않는다(§4.2 2026-08-12 개정). loud 실패는 `validate_crosswalk`의
    책임이다. 라인당 호출되는 핫패스에서 예외를 던지면 캐시에 도달하지 못하고, 상위 호출부의
    `except Exception: pass`에 조용히 삼켜져 CBM이 신호 없이 0으로 저하되기 때문이다.
    """
    p = path or CROSSWALK_PATH
    if _cache and p in _cache_store:
        return _cache_store[p]

    out: dict[str, str] = {}
    conflicted: set[str] = set()
    for key, code, raw in _iter_confirmed_goods_rows(p):
        if key in conflicted:
            continue
        prev = out.get(key)
        if prev is not None and prev != code:
            logger.warning(
                "크로스워크 충돌: 정규화키 %r 가 %r 와 %r 둘 다 가리킴 (표준키 %r). "
                "해당 키를 결정론 맵에서 제외하고 퍼지 폴백(3·4단)으로 넘긴다.",
                key, prev, code, raw,
            )
            conflicted.add(key)
            out.pop(key, None)
            continue
        out[key] = code

    if _cache:
        _cache_store[p] = out
    return out


def validate_crosswalk(path: str | None = None) -> list[dict]:
    """캐시를 우회해 파일을 다시 읽고 충돌을 찾는다. 충돌이 있으면 `CrosswalkConflictError`를
    raise한다(사람이 파일을 고치는 시점의 loud 실패, §4.2 2026-08-12 개정). 충돌이 없으면
    빈 리스트를 반환한다.
    """
    p = path or CROSSWALK_PATH
    codes_by_key: dict[str, dict[str, str]] = {}
    for key, code, raw in _iter_confirmed_goods_rows(p):
        codes_by_key.setdefault(key, {}).setdefault(code, raw)

    conflicts = [
        {"key": key, "codes": sorted(code_map), "raws": code_map}
        for key, code_map in codes_by_key.items()
        if len(code_map) > 1
    ]

    if conflicts:
        detail = "; ".join(
            f"정규화키 {c['key']!r} 가 {c['codes']!r} 둘 다 가리킴" for c in conflicts
        )
        raise CrosswalkConflictError(
            f"크로스워크 충돌 {len(conflicts)}건: {detail}. "
            "확정 행 중 하나를 정정하거나 보류로 내려야 한다."
        )
    return conflicts
