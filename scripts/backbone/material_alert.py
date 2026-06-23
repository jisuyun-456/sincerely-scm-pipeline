"""S-1b C3 자재차감 정합성 Alert (Chain E 첫 단계).

PropagationLedger 자재소요_요약 (MRP 예측) vs WMS movements 실차감 비교.
이동목적=생산투입/조립투입 (SAP 261 equivalent) 최근 N일 집계.

매칭 방법: 이동물품 필드에서 PNA 코드 추출 → PropagationLedger 프로젝트코드 매칭.
PNA 코드 없는 movements는 스킵(외부 하청 등). 매칭된 주문만 비교.

Usage:
  python scripts/backbone/material_alert.py [--days 30] [--threshold 0.5] [--dry-run]
"""
from __future__ import annotations
import argparse
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
load_dotenv()

WP = os.environ["AIRTABLE_WMS_PAT"]
WMS = "appLui4ZR5HWcQRri"
MOV_TBL = "tblwq7Kj5Y9nVjlOw"
LEDGER_TBL = "tblkQmontWGSjo8c5"

PRODUCTION_PURPOSES = {"생산투입", "조립투입"}
_PT_REQ_RE = re.compile(r"(PT\d+)×(\d+)")       # 자재소요_요약 파서
_PNA_RE = re.compile(r"\|\|\s*(PNA\d+)")          # 이동물품에서 PNA 코드 추출


def _fetch_all(tbl: str, params: dict) -> list[dict]:
    recs, off = [], None
    while True:
        p = {**params, "pageSize": 100}
        if off:
            p["offset"] = off
        r = requests.get(
            f"https://api.airtable.com/v0/{WMS}/{tbl}",
            headers={"Authorization": f"Bearer {WP}"},
            params=p,
            timeout=60,
        )
        r.raise_for_status()
        d = r.json()
        recs += d["records"]
        off = d.get("offset")
        if not off:
            break
    return recs


def fetch_ledger_by_project() -> dict[str, dict[str, int]]:
    """PropagationLedger → {프로젝트코드: {PT: 소요량}} (latest per 전파ID)."""
    recs = _fetch_all(
        LEDGER_TBL,
        {"fields[]": ["전파ID", "프로젝트코드", "자재소요_요약", "전파상태"]},
    )
    seen_pid: set[str] = set()
    # 프로젝트코드별 PT 소요 누적
    by_pna: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for rec in recs:
        f = rec["fields"]
        pid = str(f.get("전파ID") or "")
        if pid in seen_pid:
            continue
        seen_pid.add(pid)
        status = str(f.get("전파상태") or "")
        if status not in ("부분", "완결"):
            continue
        pna = str(f.get("프로젝트코드") or "").strip()
        if not pna:
            continue
        for pt, qty in _PT_REQ_RE.findall(str(f.get("자재소요_요약") or "")):
            by_pna[pna][pt] += int(qty)
    return {k: dict(v) for k, v in by_pna.items()}


def fetch_actual_by_project(days: int) -> dict[str, dict[str, int]]:
    """Recent movements (생산투입+조립투입) → {PNA: {PT: 실차감}}. PNA없는건 스킵."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    formula = (
        f"AND("
        f"OR({{이동목적}}='생산투입',{{이동목적}}='조립투입'),"
        f"IS_AFTER({{생성일자}},'{cutoff}')"
        f")"
    )
    recs = _fetch_all(
        MOV_TBL,
        {
            "filterByFormula": formula,
            "fields[]": ["파츠코드", "이동수량(변경)📝", "계획수량", "이동물품"],
        },
    )
    by_pna: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    skipped = 0
    for rec in recs:
        f = rec["fields"]
        item_str = str(f.get("이동물품") or "")
        m = _PNA_RE.search(item_str)
        if not m:
            skipped += 1
            continue
        pna = m.group(1)
        pt = str(f.get("파츠코드") or "").strip()
        if not pt:
            skipped += 1
            continue
        qty = f.get("이동수량(변경)📝") or f.get("계획수량") or 0
        by_pna[pna][pt] += int(qty)
    if skipped:
        print(f"  [INFO] PNA 코드 없는 movements {skipped}건 스킵 (외부 하청 등)")
    return {k: dict(v) for k, v in by_pna.items()}


def compute_alerts(
    actual_by_pna: dict[str, dict[str, int]],
    required_by_pna: dict[str, dict[str, int]],
    threshold: float,
) -> tuple[list[str], list[dict]]:
    """두 가지 Alert 유형.

    미착수: ledger(부분) PNA 중 실차감이 아예 없는 것 (생산 미착수 의심).
    과잉투입: 매칭된 PNA에서 실차감 > 소요 × (1+threshold).
    부족투입 per-PT는 단계적 생산으로 노이즈 과다 → 제외.
    """
    no_movement = sorted(set(required_by_pna) - set(actual_by_pna))

    over_consume = []
    matched_pnas = set(actual_by_pna) & set(required_by_pna)
    for pna in sorted(matched_pnas):
        act_pts = actual_by_pna[pna]
        req_pts = required_by_pna[pna]
        for pt, r in req_pts.items():
            if r == 0:
                continue
            a = act_pts.get(pt, 0)
            if a > r * (1 + threshold):
                over_consume.append({
                    "pna": pna,
                    "pt": pt,
                    "actual": a,
                    "required": r,
                    "ratio": round(a / r, 2),
                })
    return no_movement, over_consume


def send_slack(text: str) -> None:
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    user = os.environ.get("SLACK_DM_USER_ID", "")
    if not token or not user:
        print("[WARN] SLACK_BOT_TOKEN/SLACK_DM_USER_ID 미설정 — alert 발송 생략")
        return
    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": user, "text": text},
        timeout=10,
    )
    ok = r.json().get("ok", False)
    print(f"[SLACK] alert {'발송 완료' if ok else '실패: ' + r.text}")


def main() -> None:
    parser = argparse.ArgumentParser(description="C3 자재차감 정합성 Alert")
    parser.add_argument("--days", type=int, default=30, help="집계 기간(일)")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="허용 편차 비율 (default 0.5=±50%%)")
    parser.add_argument("--dry-run", action="store_true", help="Slack 발송 생략")
    args = parser.parse_args()

    print(f"로딩: PropagationLedger 소요 집계...", flush=True)
    required_by_pna = fetch_ledger_by_project()
    print(f"  PNA {len(required_by_pna)}건 소요 집계 완료", flush=True)

    print(f"로딩: movements (최근 {args.days}일, 생산투입+조립투입)...", flush=True)
    actual_by_pna = fetch_actual_by_project(args.days)
    print(f"  PNA {len(actual_by_pna)}건 실차감 집계 완료", flush=True)

    matched = len(set(actual_by_pna) & set(required_by_pna))
    no_movement, over_consume = compute_alerts(actual_by_pna, required_by_pna, args.threshold)

    print(f"\n=== C3 자재차감 정합성 Alert (threshold ±{args.threshold * 100:.0f}%%) ===")
    print(f"매칭 PNA: {matched}건 | 미착수 의심: {len(no_movement)}건 | 과잉투입: {len(over_consume)}건")

    if not no_movement and not over_consume:
        print("정합성 OK — 이상 없음")
        return

    lines = [
        f"*C3 자재차감 정합성 Alert*",
        f"기준: 최근 {args.days}일, 허용 ±{args.threshold * 100:.0f}%%",
        "",
    ]

    if no_movement:
        header = f"*미착수 의심* ({len(no_movement)}건) — 30일간 movements 없음:"
        print(header)
        lines.append(header)
        for pna in no_movement[:20]:  # Slack 과부하 방지
            print(f"  {pna}")
            lines.append(f"  {pna}")
        if len(no_movement) > 20:
            more = f"  ... 외 {len(no_movement) - 20}건"
            print(more)
            lines.append(more)
        lines.append("")

    if over_consume:
        header = f"*과잉투입* ({len(over_consume)}건) — 실차감 > 소요×{1 + args.threshold:.1f}:"
        print(header)
        lines.append(header)
        for d in over_consume:
            line = (
                f"  {d['pna']}  {d['pt']}  실차감 {d['actual']:,} / 소요 {d['required']:,}"
                f"  [ratio={d['ratio']}]"
            )
            print(line)
            lines.append(line.strip())

    print()
    if args.dry_run:
        print("[DRY-RUN] Slack 발송 생략")
    else:
        send_slack("\n".join(lines))


if __name__ == "__main__":
    main()
