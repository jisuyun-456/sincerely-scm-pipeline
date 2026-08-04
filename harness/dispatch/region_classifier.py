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

# 시/도 토큰이 없는 주요 랜드마크 → tier (오분류 tier5 방지). 운영 중 발견 시 확장.
_LANDMARK_REGION = {
    '연세대': 'tier1_seoul', '고려대': 'tier1_seoul', '한양대': 'tier1_seoul',
    '신촌': 'tier1_seoul', '여의도': 'tier1_seoul', '코엑스': 'tier1_seoul', 'COEX': 'tier1_seoul',
    '판교': 'tier2_이장훈_gyeonggi', '분당': 'tier2_이장훈_gyeonggi',  # 성남
}


def classify_region(address: Optional[str]) -> str:
    if not address:
        return 'unknown'
    addr = str(address).strip()
    if not addr:
        return 'unknown'

    # 경기·인천을 느슨한 '서울' contains 보다 먼저 — '경기도 …서울세관로' 류 오분류 방지.
    if '경기' in addr:
        if any(city in addr for city in IJANGHOON_GYEONGGI_CITIES):
            return 'tier2_이장훈_gyeonggi'
        return 'tier3_gyeonggi_etc'

    if '인천' in addr:
        return 'tier4_incheon'

    if '서울' in addr:
        return 'tier1_seoul'

    # 지역 토큰 없는 랜드마크 보정 (tier5 오분류 방지)
    for kw, tier in _LANDMARK_REGION.items():
        if kw in addr:
            return tier

    return 'tier5_provincial'
