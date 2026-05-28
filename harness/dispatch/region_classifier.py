"""Address rollup -> driver eligibility tier (Sub-Spec 3 Stage A 보조).

Data-driven 5-tier scheme (24-01~26-05 5,056건 분석 + P3.5 Decision 1 반영):
- tier1_seoul: 이장훈·조희선·박종성 모두 가능 (이장훈 91.6% / 조희선 74.3% / 박종성 42.7%)
- tier2_이장훈_gyeonggi: 이장훈 overflow 가능 경기 city set (사용자 명시 + 데이터 >=1건)
- tier3_gyeonggi_etc: 그 외 경기 -> 조희선·박종성만 가능
- tier4_incheon: 이장훈·조희선·박종성 모두 가능 (P3.5 Decision 1: 사용자 결정)
- tier5_provincial: 박종성 only (전국 데이터 cover) -> fallback spillover_로젠
- unknown: 주소 NULL -> 수동 처리
"""
from typing import Optional

IJANGHOON_GYEONGGI_CITIES = frozenset({
    '구리', '광명', '성남', '고양',
    '하남', '부천', '안양', '과천', '안산',
    '군포', '남양주', '수원',
})


def classify_region(address: Optional[str]) -> str:
    if not address:
        return 'unknown'
    addr = str(address)

    if '서울' in addr:
        return 'tier1_seoul'

    if '경기' in addr:
        if any(city in addr for city in IJANGHOON_GYEONGGI_CITIES):
            return 'tier2_이장훈_gyeonggi'
        return 'tier3_gyeonggi_etc'

    if '인천' in addr:
        return 'tier4_incheon'

    return 'tier5_provincial'
