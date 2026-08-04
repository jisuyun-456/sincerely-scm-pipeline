"""Tests for harness.dispatch.region_classifier (Contract C1·C3 보조)."""
from __future__ import annotations

import pytest

from harness.dispatch.region_classifier import IJANGHOON_GYEONGGI_CITIES, classify_region


class TestRegionClassifier:
    """5 tier 분류 + P3.5 Decision 1 (인천=모두 가능)."""

    @pytest.mark.parametrize('addr,expected', [
        ('서울특별시 강남구 테헤란로 152', 'tier1_seoul'),
        ('서울 마포구', 'tier1_seoul'),
    ])
    def test_tier1_seoul(self, addr, expected):
        assert classify_region(addr) == expected

    @pytest.mark.parametrize('addr,expected', [
        ('경기 광명시', 'tier2_이장훈_gyeonggi'),
        ('경기도 성남시 분당구', 'tier2_이장훈_gyeonggi'),
        ('경기 고양시 일산서구', 'tier2_이장훈_gyeonggi'),
    ])
    def test_tier2_ijanghoon_gyeonggi(self, addr, expected):
        assert classify_region(addr) == expected

    @pytest.mark.parametrize('addr,expected', [
        ('경기 화성시 동탄', 'tier3_gyeonggi_etc'),
        ('경기도 평택시', 'tier3_gyeonggi_etc'),
    ])
    def test_tier3_gyeonggi_etc(self, addr, expected):
        assert classify_region(addr) == expected

    def test_tier4_incheon(self):
        # P3.5 Decision 1: 인천은 모든 driver 가능
        assert classify_region('인천광역시 연수구 송도동') == 'tier4_incheon'

    @pytest.mark.parametrize('addr', [
        '부산광역시 해운대구',
        '충청북도 청주시',
        '제주특별자치도 제주시',
    ])
    def test_tier5_provincial(self, addr):
        assert classify_region(addr) == 'tier5_provincial'

    @pytest.mark.parametrize('addr', [None, ''])
    def test_unknown(self, addr):
        assert classify_region(addr) == 'unknown'

    def test_ijanghoon_cities_includes_user_specified(self):
        for must in ('구리', '광명', '성남', '고양'):
            assert must in IJANGHOON_GYEONGGI_CITIES


class TestRegionFixes:
    """AUDIT (2026-06-23) — 랜드마크 보정 + 느슨한 서울 오분류 + strip."""

    @pytest.mark.parametrize('addr,expected', [
        ('연세대학교 신촌캠퍼스 대우관', 'tier1_seoul'),
        ('고려대학교 안암동', 'tier1_seoul'),
        ('판교테크노밸리 유스페이스', 'tier2_이장훈_gyeonggi'),
    ])
    def test_landmark_resolves(self, addr, expected):
        assert classify_region(addr) == expected

    def test_gyeonggi_with_seoul_streetname_not_misclassified(self):
        # '서울'이 도로명에 들어가도 경기 우선
        assert classify_region('경기도 광주시 서울세관로 12') == 'tier3_gyeonggi_etc'

    @pytest.mark.parametrize('addr', ['   ', '\t'])
    def test_whitespace_only_is_unknown(self, addr):
        assert classify_region(addr) == 'unknown'
