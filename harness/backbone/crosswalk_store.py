"""굿즈명↔견적코드 결정론 크로스워크 로더 (git-SSOT).

spec: docs/superpowers/specs/2026-08-12-bridge-cbm-crosswalk-design.md §4.2~4.3

SSOT = data/crosswalk/goods_crosswalk.csv (git 추적). 크로스워크는 **신원 매핑만**
보유하며 CBM 값을 저장하지 않는다 — CBM SSOT는 TMS Product다.

검증상태='확정' ∧ 키유형='굿즈명' 행만 결정론 맵에 적재한다. 같은 정규화 키에
서로 다른 견적코드를 가진 확정 행이 있으면 조용히 last-wins 하지 않고 loud 실패한다.
"""
from __future__ import annotations

import csv
import os

from harness.backbone.keys import normalize_goods

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
    """조회 키 정규화 — normalize_goods 후 공백 제거·casefold."""
    return normalize_goods(raw or "").strip().casefold()


def clear_cache() -> None:
    _cache_store.clear()


def load_crosswalk(path: str | None = None, *, _cache: bool = True) -> dict[str, str]:
    """정규화키 → 견적코드(upper). 확정·굿즈명 행만. 파일 없으면 {}.

    파일 부재를 정상으로 취급하는 것은 의도적이다 — 크로스워크 미배포 환경에서
    1.5단이 자동 무력화되고 기존 1~4단 동작이 그대로 유지된다(spec §4.3, §10).
    """
    p = path or CROSSWALK_PATH
    if _cache and p in _cache_store:
        return _cache_store[p]

    out: dict[str, str] = {}
    if os.path.exists(p):
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
                prev = out.get(key)
                if prev is not None and prev != code:
                    raise CrosswalkConflictError(
                        f"크로스워크 충돌: 정규화키 {key!r} 가 {prev!r} 와 {code!r} 둘 다 가리킴 "
                        f"(표준키 {raw!r}). 확정 행 중 하나를 정정하거나 보류로 내려야 한다."
                    )
                out[key] = code

    if _cache:
        _cache_store[p] = out
    return out
