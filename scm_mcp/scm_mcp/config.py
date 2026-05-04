import os

AIRTABLE_PAT = os.environ.get("AIRTABLE_PAT") or os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_URL = "https://api.airtable.com/v0"
AIRTABLE_CONTENT_URL = "https://content.airtable.com/v0"

WMS_BARCODE_BASE = "app4LvuNIDiqTmhnv"
WMS_MATERIAL_BASE = "appLui4ZR5HWcQRri"
TMS_BASE = "app4x70a8mOrIKsMf"

TABLES: dict[str, tuple[str, str]] = {
    "movement":           (WMS_MATERIAL_BASE, "tblwq7Kj5Y9nVjlOw"),
    "material":           (WMS_MATERIAL_BASE, "tblaRpZstW10EwDlo"),
    "sync_parts":         (WMS_MATERIAL_BASE, "tblzJh0V4hdo4Xbvx"),
    "logistics_release":  (WMS_MATERIAL_BASE, "tbler5LBLxh8lcEPv"),
    "picking_list":     (WMS_BARCODE_BASE,  "tblnxU0PlegXT7bYj"),
    "barcode":          (WMS_BARCODE_BASE,  "tbl0K3QP5PCd06Cxv"),
    "outbound_confirm": (WMS_BARCODE_BASE,  "tblMQG1PYioIUWdbe"),
    "shipment":         (TMS_BASE,          "tbllg1JoHclGYer7m"),
    "delivery_event":   (TMS_BASE,          "tblQyuAW30yf21WEf"),
    "otif":             (TMS_BASE,          "tbl4WfEuGLDlqCTQH"),
}

BASE_ALIAS: dict[str, str] = {
    "wms_barcode":  WMS_BARCODE_BASE,
    "wms_material": WMS_MATERIAL_BASE,
    "tms":          TMS_BASE,
}
