#!/usr/bin/env python3
"""WMS AutoResearch → Obsidian Vault 동기화 스크립트.

GitHub Actions가 매주 월요일 11:00 KST에 실행한 WMS 주간 분석 결과를
Obsidian Vault의 _AutoResearch/WMS/ 경로로 복사한다.

Usage:
    python scripts/sync_wms_to_obsidian.py           # git pull 포함
    python scripts/sync_wms_to_obsidian.py --no-pull  # git pull 없이 복사만
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
WMS_OUTPUTS = REPO_ROOT / "_AutoResearch" / "WMS" / "outputs"
WMS_WIKI    = REPO_ROOT / "_AutoResearch" / "WMS" / "wiki"

VAULT_ROOT    = Path(r"C:\Users\yjisu\Documents\ClaudeVault")
VAULT_OUTPUTS = VAULT_ROOT / "_AutoResearch" / "WMS" / "outputs"
VAULT_WIKI    = VAULT_ROOT / "_AutoResearch" / "WMS" / "wiki"

LOG_PATH = REPO_ROOT / "_AutoResearch" / "WMS" / "sync_log.txt"


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def git_pull() -> bool:
    """git pull 실행. 성공 시 True."""
    _log("git pull 실행 중...")
    result = subprocess.run(
        ["git", "pull", "--ff-only"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        _log(f"git pull 완료: {result.stdout.strip()}")
        return True
    else:
        _log(f"git pull 실패: {result.stderr.strip()}")
        return False


def sync_directory(src: Path, dst: Path) -> list[str]:
    """src의 모든 .md 파일을 dst로 복사. 복사된 파일명 목록 반환."""
    if not src.exists():
        _log(f"소스 없음: {src}")
        return []
    dst.mkdir(parents=True, exist_ok=True)
    copied = []
    for src_file in sorted(src.glob("*.md")):
        dst_file = dst / src_file.name
        dst_needs_update = (
            not dst_file.exists()
            or src_file.stat().st_mtime > dst_file.stat().st_mtime
        )
        if dst_needs_update:
            shutil.copy2(src_file, dst_file)
            copied.append(src_file.name)
            _log(f"  복사: {src_file.name} → {dst_file}")
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description="WMS AutoResearch → Obsidian 동기화")
    parser.add_argument("--no-pull", action="store_true", help="git pull 없이 복사만 수행")
    args = parser.parse_args()

    _log("=== WMS Obsidian 동기화 시작 ===")

    if not VAULT_ROOT.exists():
        _log(f"Obsidian Vault 없음: {VAULT_ROOT}. 종료.")
        sys.exit(1)

    if not args.no_pull:
        if not git_pull():
            _log("git pull 실패. --no-pull 로 재시도하거나 네트워크를 확인하세요.")
            sys.exit(1)

    copied_outputs = sync_directory(WMS_OUTPUTS, VAULT_OUTPUTS)
    copied_wiki    = sync_directory(WMS_WIKI,    VAULT_WIKI)

    total = len(copied_outputs) + len(copied_wiki)
    if total == 0:
        _log("신규 파일 없음. 이미 최신 상태.")
    else:
        _log(f"=== 완료: outputs {len(copied_outputs)}개 + wiki {len(copied_wiki)}개 복사 ===")


if __name__ == "__main__":
    main()
