"""
FastAPI 웹훅 서버 — Railway 배포용
GitHub Actions (generate-barcode-pdf, generate-pdf) 대체

엔드포인트:
  POST /generate-barcode-pdf  → Barcode 베이스 (출고확인서/피킹리스트/라벨지)
  POST /generate-tms-pdf      → TMS 베이스 (출고확인서_tms)
  GET  /health                → 헬스체크
"""

import os, subprocess, sys
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

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


# ── 엔드포인트 ───────────────────────────────────────────────────────────────

@app.post("/generate-barcode-pdf")
def generate_barcode_pdf(
    payload: BarcodeRequest,
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

    return _run(cmd)


@app.post("/generate-tms-pdf")
def generate_tms_pdf(
    payload: TMSRequest,
    x_webhook_secret: str = Header(default=""),
):
    """TMS 베이스: 출고확인서_tms"""
    _check_secret(x_webhook_secret)
    cmd = [sys.executable, "pdf/출고확인서_tms.py", "--record-id", payload.record_id]
    return _run(cmd)


@app.get("/health")
def health():
    return {"status": "ok"}
