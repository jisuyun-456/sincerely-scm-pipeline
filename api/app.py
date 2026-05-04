"""
FastAPI 웹훅 서버 — Railway 배포용
GitHub Actions (generate-barcode-pdf, generate-pdf) 대체

엔드포인트:
  POST /generate-barcode-pdf  → Barcode 베이스 (출고확인서/피킹리스트/라벨지)
  POST /generate-tms-pdf      → TMS 베이스 (출고확인서_tms)
  POST /generate-wms-pdf      → WMS 출고서류 3종 (carton_label/packing_list/shipping_mark)
  POST /generate-pkg-label    → pkg_schedule 투입자재 피킹 라벨
  GET  /health                → 헬스체크
"""

import logging, os, subprocess, sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from pydantic import BaseModel

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

REPO_ROOT      = Path(__file__).parent.parent
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


# ── 요청 모델 ────────────────────────────────────────────────────────────────

class BarcodeRequest(BaseModel):
    pdf_type:  str
    record_id: str = ""
    bc_id:     str = ""

class TMSRequest(BaseModel):
    record_id: str

class WMSRequest(BaseModel):
    record_id: str
    pdf_type:  str = "all"   # "all" | "carton_label" | "packing_list" | "shipping_mark"

class PkgLabelRequest(BaseModel):
    record_id: str


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────

def _check_secret(token: str):
    if WEBHOOK_SECRET and token != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _run(cmd: list[str]) -> dict:
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PDF_OUTPUT_DIR": "/tmp"},
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr[-500:])
    return {"status": "ok", "log": result.stdout[-300:]}


def _run_bg(cmd: list[str]):
    logger.info(f"[BG] starting: {cmd}")
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "PDF_OUTPUT_DIR": "/tmp"},
    )
    if result.returncode != 0:
        logger.error(f"[BG] FAILED rc={result.returncode}: {result.stderr[-1200:]}")
    else:
        out = (result.stdout + result.stderr)[-2000:]
        logger.info(f"[BG] OK: {out}")


# ── 엔드포인트 ───────────────────────────────────────────────────────────────

@app.post("/generate-barcode-pdf")
def generate_barcode_pdf(
    payload: BarcodeRequest,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str = Header(default=""),
):
    """Barcode 베이스: 출고확인서 / 피킹리스트 / 라벨지"""
    _check_secret(x_webhook_secret)

    py = sys.executable
    t  = payload.pdf_type

    if t == "출고확인서":
        cmd = [py, "scripts/출고확인서_pdf.py", "--record-id", payload.record_id]

    elif t == "피킹리스트":
        cmd = [py, "scripts/picking_list_pdf.py", "--record-id", payload.record_id]

    elif t == "라벨지":
        if payload.bc_id and payload.record_id:
            cmd = [py, "scripts/barcode_label.py",
                   "--bc-id", payload.bc_id, "--record-id", payload.record_id]
        elif payload.bc_id:
            cmd = [py, "scripts/barcode_label.py",
                   "--bc-id", payload.bc_id, "--no-upload"]
        else:
            cmd = [py, "scripts/barcode_label.py", "--record-id", payload.record_id]

    else:
        raise HTTPException(status_code=400, detail=f"Unknown pdf_type: {t}")

    background_tasks.add_task(_run_bg, cmd)
    return {"status": "accepted"}


@app.post("/generate-tms-pdf")
def generate_tms_pdf(
    payload: TMSRequest,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str = Header(default=""),
):
    """TMS 베이스: 출고확인서_tms"""
    _check_secret(x_webhook_secret)
    logger.info(f"[TMS] request: record_id={payload.record_id!r}")
    if not payload.record_id:
        raise HTTPException(status_code=400, detail="record_id is required")
    cmd = [sys.executable, "pdf/출고확인서_tms.py", "--record-id", payload.record_id]
    background_tasks.add_task(_run_bg, cmd)
    return {"status": "accepted"}


@app.post("/generate-wms-pdf")
def generate_wms_pdf(
    payload: WMSRequest,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str = Header(default=""),
):
    """WMS 출고서류 3종: carton_label / packing_list / shipping_mark / all"""
    _check_secret(x_webhook_secret)
    logger.info(f"[WMS] request: record_id={payload.record_id!r} pdf_type={payload.pdf_type!r}")
    if not payload.record_id:
        raise HTTPException(status_code=400, detail="record_id is required")
    background_tasks.add_task(_run_wms_all, payload.record_id, payload.pdf_type)
    return {"status": "accepted"}


def _run_wms_all(record_id: str, pdf_type: str):
    py = sys.executable
    carton_fld  = os.getenv("CARTON_LABEL_FIELD_ID", "")
    packing_fld = os.getenv("PACKING_LIST_FIELD_ID", "")
    shipping_fld = os.getenv("SHIPPING_MARK_FIELD_ID", "")

    tasks = {
        "carton_label":  [py, "scripts/outer_box_label.py",
                          "--lr-id", record_id, "--style", "global",
                          "--upload-field", carton_fld],
        "packing_list":  [py, "scripts/packing_list.py",
                          "--lr-id", record_id,
                          "--upload-field", packing_fld],
        "shipping_mark": [py, "scripts/shipping_mark.py",
                          "--lr-id", record_id,
                          "--upload-field", shipping_fld],
    }
    to_run = list(tasks.values()) if pdf_type == "all" else [tasks[pdf_type]]
    for cmd in to_run:
        _run_bg(cmd)


@app.post("/generate-pkg-label")
def generate_pkg_label(
    payload: PkgLabelRequest,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str = Header(default=""),
):
    """pkg_schedule 투입자재 피킹 라벨 (80×55mm)"""
    _check_secret(x_webhook_secret)
    logger.info(f"[PKG] request: record_id={payload.record_id!r}")
    if not payload.record_id:
        raise HTTPException(status_code=400, detail="record_id is required")
    cmd = [sys.executable, "scripts/pkg_schedule_label.py",
           "--record-id", payload.record_id]
    background_tasks.add_task(_run_bg, cmd)
    return {"status": "accepted"}


@app.get("/trigger-wms-pdf")
def trigger_wms_pdf_get(
    record_id: str,
    background_tasks: BackgroundTasks,
    token: str = "",
    pdf_type: str = "all",
):
    """WMS 출고서류 GET 트리거 — Interface 'Open URL' 버튼용"""
    _check_secret(token)
    if not record_id:
        raise HTTPException(status_code=400, detail="record_id is required")
    background_tasks.add_task(_run_wms_all, record_id, pdf_type)
    return {"status": "accepted"}


@app.get("/trigger-pkg-label")
def trigger_pkg_label_get(
    record_id: str,
    background_tasks: BackgroundTasks,
    token: str = "",
):
    """pkg_schedule 투입자재 라벨 GET 트리거 — Interface 'Open URL' 버튼용"""
    _check_secret(token)
    if not record_id:
        raise HTTPException(status_code=400, detail="record_id is required")
    cmd = [sys.executable, "scripts/pkg_schedule_label.py",
           "--record-id", record_id]
    background_tasks.add_task(_run_bg, cmd)
    return {"status": "accepted"}


@app.get("/trigger-customer-goods-label")
def trigger_customer_goods_label_get(
    record_id: str,
    background_tasks: BackgroundTasks,
    token: str = "",
):
    """고객물품 라벨 GET 트리거 — Interface 'Open URL' 버튼용"""
    _check_secret(token)
    if not record_id:
        raise HTTPException(status_code=400, detail="record_id is required")
    cmd = [sys.executable, "scripts/customer_goods_label.py", "--record-id", record_id]
    background_tasks.add_task(_run_bg, cmd)
    return {"status": "accepted"}


@app.get("/trigger-inbound-label")
def trigger_inbound_label_get(
    record_id: str,
    background_tasks: BackgroundTasks,
    token: str = "",
):
    """입고 라벨 GET 트리거 — Interface 'Open URL' 버튼용"""
    _check_secret(token)
    if not record_id:
        raise HTTPException(status_code=400, detail="record_id is required")
    cmd = [sys.executable, "scripts/inbound_label.py", "--record-id", record_id]
    background_tasks.add_task(_run_bg, cmd)
    return {"status": "accepted"}


@app.get("/health")
def health():
    return {"status": "ok"}
