"""P0: AirtableClient 쓰기 allowlist — ⚡미러/MES/SERPA 쓰기 차단."""
import pytest

from harness._core.airtable import AirtableClient, WriteForbiddenError

WMS = "appLui4ZR5HWcQRri"
TMS = "app4x70a8mOrIKsMf"
WMS_ITEMMASTER = "tbl5ZGY373D5SCONV"   # 네이티브 — 허용
MIRROR_ORDER = "tblJslWg8sYEdCkXw"     # ⚡order 미러 — 금지
SHIPMENT = "tbllg1JoHclGYer7m"         # TMS Shipment — 허용 (estimated_cbm)


def test_mirror_table_patch_forbidden():
    c = AirtableClient.get_or_create(WMS, MIRROR_ORDER, "pat-test")
    with pytest.raises(WriteForbiddenError):
        c.patch_record("rec123", {"x": 1})


def test_mirror_table_create_forbidden():
    c = AirtableClient.get_or_create(WMS, MIRROR_ORDER, "pat-test")
    with pytest.raises(WriteForbiddenError):
        c.create_records([{"fields": {"x": 1}}])


def test_native_wms_table_passes_guard(monkeypatch):
    c = AirtableClient.get_or_create(WMS, WMS_ITEMMASTER, "pat-test")
    called = {}

    def fake_patch(path, json, headers):
        called["ok"] = True

        class R:
            def json(self_):
                return {"id": "rec1", "fields": json["fields"]}

        return R()

    monkeypatch.setattr(c._session, "patch", fake_patch)
    c.patch_record("rec1", {"CBM_개당_m3": 0.02})
    assert called.get("ok")


def test_shipment_allowed():
    c = AirtableClient.get_or_create(TMS, SHIPMENT, "pat-test")
    assert c._write_allowed() is True


def test_mirror_not_allowed_flag():
    c = AirtableClient.get_or_create(WMS, MIRROR_ORDER, "pat-test")
    assert c._write_allowed() is False
