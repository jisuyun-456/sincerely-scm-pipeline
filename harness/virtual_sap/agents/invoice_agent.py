"""Phase F — 세금계산서 자동 발행 에이전트.

Trigger: fi_document.doc_type='SD' (매출 전표) 중 아직 invoice 이벤트가 없는 건.
Action:  sim_invoice 테이블에 인보이스 레코드 INSERT + Slack 알림.
         금액 = fi_document_line 의 Revenue(4110) Credit 합계, VAT = 금액 × 10%.
"""
from __future__ import annotations

import logging
import os
import sys
import json
import urllib.request
from datetime import datetime, timezone

if __name__ == "__main__" and __package__ is None:
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
    __package__ = "harness.virtual_sap.agents"

from .. import supabase_client as db
from ..config import get_config

logger = logging.getLogger(__name__)

AGENT_NAME = "세금계산서발행"
REVENUE_GL = "4110"
VAT_RATE = 0.10


def run() -> int:
    cfg = get_config()
    dry_run = cfg.dry_run

    # SD-type FI documents (sales revenue postings)
    sd_docs = db.select(
        "fi_document",
        {"doc_type": "SD", "is_reversal": False},
        columns="fi_doc_id, source_mat_doc_id, period, posting_date",
    )
    if not sd_docs:
        logger.info("%s: no SD fi_documents found", AGENT_NAME)
        return 0

    prior = db.select("sim_agent_event", {"agent_name": AGENT_NAME}, columns="target_id")
    already_done = {r["target_id"] for r in prior if r.get("target_id")}

    pending = [d for d in sd_docs if d["fi_doc_id"] not in already_done]
    if not pending:
        logger.info("%s: all SD docs already invoiced", AGENT_NAME)
        return 0

    # Batch-fetch fi_document_lines for pending docs
    fi_doc_ids = [d["fi_doc_id"] for d in pending]
    all_lines = db.select(
        "fi_document_line",
        filters={"fi_doc_id": fi_doc_ids},
        columns="fi_doc_id, gl_code, debit_credit, amount_local, partner_id",
    )
    lines_by_doc: dict[str, list[dict]] = {}
    for line in all_lines:
        lines_by_doc.setdefault(line["fi_doc_id"], []).append(line)

    # Resolve mat_doc → SO → customer
    mat_doc_ids = [d["source_mat_doc_id"] for d in pending if d.get("source_mat_doc_id")]
    mat_docs = db.select("mat_document", filters={"mat_doc_id": mat_doc_ids},
                         columns="mat_doc_id, source_doc_type, source_doc_id") if mat_doc_ids else []
    mat_to_so = {
        r["mat_doc_id"]: r["source_doc_id"]
        for r in mat_docs if r.get("source_doc_type") == "SO"
    }

    so_ids = list(set(v for v in mat_to_so.values() if v))
    so_rows = db.select("sales_order", filters={"so_id": so_ids},
                        columns="so_id, customer_id") if so_ids else []
    so_to_customer = {r["so_id"]: r["customer_id"] for r in so_rows}

    processed = 0
    slack_lines: list[str] = []

    for fi_doc in pending:
        fi_doc_id = fi_doc["fi_doc_id"]
        mat_doc_id = fi_doc.get("source_mat_doc_id")
        so_id = mat_to_so.get(mat_doc_id) if mat_doc_id else None
        customer_id = so_to_customer.get(so_id) if so_id else None

        # Revenue amount = sum of Credit lines on Revenue GL
        lines = lines_by_doc.get(fi_doc_id, [])
        amount = sum(
            float(ln["amount_local"])
            for ln in lines
            if ln.get("gl_code") == REVENUE_GL and ln.get("debit_credit") == "C"
        )
        if amount <= 0:
            # Fallback: any credit line total
            amount = sum(
                float(ln["amount_local"])
                for ln in lines
                if ln.get("debit_credit") == "C"
            )

        if amount <= 0:
            logger.debug("%s: skipping %s — zero amount", AGENT_NAME, fi_doc_id)
            continue

        tax_amount = round(amount * VAT_RATE, 2)
        total_amount = round(amount + tax_amount, 2)

        db.insert("sim_invoice", {
            "fi_doc_id": fi_doc_id,
            "so_id": so_id,
            "customer_id": customer_id,
            "amount": round(amount, 2),
            "tax_amount": tax_amount,
            "total_amount": total_amount,
            "status": "issued",
        }, dry_run=dry_run)

        msg = (
            f"FI {fi_doc_id} | SO {so_id or '—'} | 고객 {customer_id or '—'} | "
            f"공급가 ₩{amount:,.0f} + VAT ₩{tax_amount:,.0f} = ₩{total_amount:,.0f}"
        )
        logger.info("%s: %s", AGENT_NAME, msg)
        db.insert("sim_agent_event", {
            "agent_name": AGENT_NAME,
            "target_id": fi_doc_id,
            "status": "ok",
            "message": msg,
            "sim_run_id": None,
        }, dry_run=dry_run)
        slack_lines.append(f"🧾 {fi_doc_id[:12]}... | {customer_id or '—'} | ₩{total_amount:,.0f}")
        processed += 1

    if slack_lines:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        _slack_notify(
            f"🧾 *세금계산서 발행 에이전트* ({ts})\n"
            + "\n".join(slack_lines)
            + f"\n총 {processed}건 발행 완료"
        )

    logger.info("%s: %d invoice(s) issued", AGENT_NAME, processed)
    return processed


def _slack_notify(text: str) -> None:
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    user = os.environ.get("SLACK_DM_USER_ID", "")
    if not token or not user:
        return
    body = json.dumps({"channel": user, "text": text}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        if not result.get("ok"):
            logger.warning("Slack error: %s", result.get("error"))
    except Exception as exc:
        logger.warning("Slack notify failed: %s", exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    count = run()
    print(f"{AGENT_NAME}: {count} invoice(s) issued")
    sys.exit(0)
