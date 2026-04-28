# STOCK 리포트 강화 + TMS Obsidian 동기화 + Antigravity 분리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** STOCK 일일 리포트에 누적수익률·MDD·포지션 에이징 섹션 추가, TMS AutoResearch 결과를 Obsidian으로 자동 동기화, Antigravity에서 SCM/STOCK 프로젝트 독립 설명 제공.

**Architecture:**
- Task 1: `STOCK_WORK/scripts/daily_analysis.py`에 4개 섹션 추가 (run_cycle.py는 이미 Obsidian 자동 복사 완료 - 라인 1354~1360)
- Task 2: `SCM_WORK/scripts/sync_tms_to_obsidian.py` 신규 작성 + Windows 작업 스케줄러 등록
- Task 3: Antigravity 창 분리 방법 + .claude/ 독립성 설명 (코드 변경 없음)

**Tech Stack:** Python 3.11, pathlib, shutil, json, Windows Task Scheduler (schtasks.exe)

---

## 현재 상태 확인 (중요)

- `run_cycle.py:1354-1360` — phase_report()에서 이미 `generate_daily_analysis()` + `copy_to_obsidian()` 자동 실행됨 (ClaudeVault 존재 시)
- `STOCK_WORK/scripts/daily_analysis.py` — Obsidian 경로: `ClaudeVault/STOCK/DailyReport/`
- `ClaudeVault/_AutoResearch/SCM/outputs/` — 폴더 존재하나 비어 있음 (SCM_WORK 로컬 outputs과 별도)
- `STOCK_WORK/.claude/` and `SCM_WORK/.claude/` — 이미 프로젝트별 완전 독립

---

## File Map

| 작업 | 파일 | 변경 유형 |
|------|------|---------|
| Task 1 | `STOCK_WORK/scripts/daily_analysis.py` | Modify (섹션 4개 추가) |
| Task 2 | `SCM_WORK/scripts/sync_tms_to_obsidian.py` | Create |
| Task 2 | Windows Task Scheduler 등록 | schtasks 명령 실행 |

---

## Task 1: daily_analysis.py — 섹션 4개 추가

**Files:**
- Modify: `c:/Users/yjisu/Desktop/STOCK_WORK/scripts/daily_analysis.py`

### 추가할 섹션 목록
1. `## Today's P&L` — 오늘 전체 계좌 일간 손익 (금액 + %)
2. `## Cumulative Return by Strategy` — 전략별 누적 수익률 (inception 대비 %)
3. `## Max Drawdown by Strategy` — 전략별 MDD (nav_history 기반)
4. `## Open Position Aging` — 포지션별 보유 기간 (trade_log에서 매수일 추적)

- [ ] **Step 1: daily_analysis.py 현재 상태 확인 후 헬퍼 함수 4개 추가**

`generate_daily_analysis()` 함수 내부, `# ---- Build markdown ----` 블록 직전에 아래 헬퍼 추가:

```python
def _calc_daily_pnl(portfolios: dict, account: dict) -> tuple[float, float]:
    """오늘 NAV - 어제 NAV로 일간 손익 계산."""
    total_today = 0.0
    total_yesterday = 0.0
    for code in ["MOM", "VAL", "QNT", "LEV", "LEV_ST"]:
        strat = portfolios.get("strategies", {}).get(code, {})
        nav_history = strat.get("nav_history", [])
        if len(nav_history) >= 2:
            total_today += nav_history[-1]["nav"]
            total_yesterday += nav_history[-2]["nav"]
        elif len(nav_history) == 1:
            total_today += nav_history[-1]["nav"]
            total_yesterday += nav_history[-1]["nav"]
    daily_pnl = total_today - total_yesterday
    daily_pnl_pct = (daily_pnl / total_yesterday * 100) if total_yesterday > 0 else 0.0
    return daily_pnl, daily_pnl_pct


def _calc_cumulative_returns(portfolios: dict) -> list[tuple[str, float, float, float]]:
    """전략별 누적 수익률. Returns: [(code, inception_nav, current_nav, pct), ...]"""
    results = []
    inception = portfolios.get("inception", {}).get("strategies", {})
    for code in ["MOM", "VAL", "QNT", "LEV", "LEV_ST"]:
        strat = portfolios.get("strategies", {}).get(code, {})
        nav_history = strat.get("nav_history", [])
        inception_nav = inception.get(code, strat.get("allocated", 0))
        current_nav = nav_history[-1]["nav"] if nav_history else strat.get("allocated", inception_nav)
        pct = ((current_nav - inception_nav) / inception_nav * 100) if inception_nav > 0 else 0.0
        results.append((code, inception_nav, current_nav, pct))
    return results


def _calc_mdd(portfolios: dict) -> list[tuple[str, float, str, str]]:
    """전략별 MDD. Returns: [(code, mdd_pct, peak_date, trough_date), ...]"""
    results = []
    for code in ["MOM", "VAL", "QNT", "LEV", "LEV_ST"]:
        strat = portfolios.get("strategies", {}).get(code, {})
        nav_history = strat.get("nav_history", [])
        if len(nav_history) < 2:
            results.append((code, 0.0, "-", "-"))
            continue
        navs = [h["nav"] for h in nav_history]
        dates = [h["date"] for h in nav_history]
        peak = navs[0]
        peak_date = dates[0]
        max_dd = 0.0
        trough_date = dates[0]
        for i, (nav, date) in enumerate(zip(navs, dates)):
            if nav > peak:
                peak = nav
                peak_date = date
            dd = (nav - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd
                trough_date = date
        results.append((code, max_dd, peak_date, trough_date))
    return results


def _calc_position_aging(
    positions: list[dict], sym_map: dict[str, str]
) -> list[tuple[str, str, int, float]]:
    """포지션별 보유 기간. trade_log에서 최초 매수일 찾아 계산.
    Returns: [(symbol, strategy, days_held, unrealized_plpc), ...]
    """
    from datetime import date as _date
    today = _date.today()
    buy_dates: dict[str, str] = {}
    if TRADE_LOG_PATH.exists():
        with open(TRADE_LOG_PATH) as f:
            for line in f:
                entry = json.loads(line.strip())
                if entry.get("side") == "buy" and entry.get("status") in ("submitted", "filled"):
                    sym = entry.get("symbol", "")
                    ts = entry.get("ts", "")[:10]  # YYYY-MM-DD
                    if sym and sym not in buy_dates:
                        buy_dates[sym] = ts
    result = []
    for p in sorted(positions, key=lambda x: x.get("symbol", "")):
        sym = p.get("symbol", "")
        strat = sym_map.get(sym, "?")
        buy_date_str = buy_dates.get(sym)
        if buy_date_str:
            try:
                buy_dt = _date.fromisoformat(buy_date_str)
                days = (today - buy_dt).days
            except ValueError:
                days = 0
        else:
            days = 0
        plpc = p.get("unrealized_plpc", 0.0)
        result.append((sym, strat, days, plpc))
    return result
```

- [ ] **Step 2: generate_daily_analysis() 내에 새 섹션 4개 삽입**

`generate_daily_analysis()` 함수 내, `# ---- Build markdown ----` 아래 `lines.append(f"# Daily Analysis - {date_str}")` 직후에:

```python
    # ---- 새 섹션 데이터 계산 ----
    daily_pnl, daily_pnl_pct = _calc_daily_pnl(portfolios, account)
    cumulative = _calc_cumulative_returns(portfolios)
    mdd_data = _calc_mdd(portfolios)
    aging_data = _calc_position_aging(positions, sym_map) if positions else []
```

그리고 `## Market Regime` 섹션 **이후**, `## Market Summary` **이전**에:

```python
    # Today's P&L
    sign = "+" if daily_pnl >= 0 else ""
    lines.append(f"## Today's P&L: {sign}${daily_pnl:,.2f} ({sign}{daily_pnl_pct:.2f}%)")
    lines.append("")
```

`## Portfolio Performance` 테이블 **이후**, `## Top 5 Performers` **이전**에:

```python
    # Cumulative Return by Strategy
    lines.append("## Cumulative Return by Strategy")
    lines.append("| Strategy | Inception NAV | Current NAV | Return |")
    lines.append("|----------|--------------|------------|--------|")
    for code, inception_nav, current_nav, pct in cumulative:
        sign = "+" if pct >= 0 else ""
        lines.append(f"| {code} | ${inception_nav:,.0f} | ${current_nav:,.0f} | {sign}{pct:.2f}% |")
    lines.append("")

    # Max Drawdown by Strategy
    lines.append("## Max Drawdown by Strategy")
    lines.append("| Strategy | MDD | Peak Date | Trough Date |")
    lines.append("|----------|-----|-----------|-------------|")
    for code, mdd, peak_d, trough_d in mdd_data:
        flag = " ⚠️" if mdd < -10 else ""
        lines.append(f"| {code} | {mdd:.1f}%{flag} | {peak_d} | {trough_d} |")
    lines.append("")
```

`## Risk Alerts` **이후**, `## Tomorrow Outlook` **이전**에:

```python
    # Open Position Aging
    if aging_data:
        lines.append("## Open Position Aging")
        lines.append("| Symbol | Strategy | Days Held | Unrealized P&L% | Note |")
        lines.append("|--------|----------|-----------|----------------|------|")
        for sym, strat, days, plpc in aging_data:
            note = ""
            if days >= 60:
                note = "⚠️ Review (60d+)"
            elif plpc < -0.10:
                note = "⚠️ Near stop-loss"
            lines.append(f"| {sym} | {strat} | {days}d | {plpc:+.1%} | {note} |")
        lines.append("")
```

- [ ] **Step 3: 자동화 검증 — run_cycle.py 라인 1354~1360 확인**

```bash
grep -n "copy_to_obsidian\|generate_daily_analysis\|ClaudeVault" c:/Users/yjisu/Desktop/STOCK_WORK/run_cycle.py
```

Expected output: 라인 1354~1360에 이미 자동 호출 로직 존재 확인.

- [ ] **Step 4: 수동 테스트 실행**

```bash
cd c:/Users/yjisu/Desktop/STOCK_WORK
python scripts/daily_analysis.py --obsidian
```

Expected: 
```
[Daily Analysis] Generating report for 2026-04-15...
  Report saved: reports/daily/2026-04-15-analysis.md
  Copied to Obsidian: C:\Users\yjisu\Documents\ClaudeVault\STOCK\DailyReport\2026-04-15-analysis.md
```

- [ ] **Step 5: Obsidian에서 파일 내용 확인**

```bash
cat "c:/Users/yjisu/Documents/ClaudeVault/STOCK/DailyReport/2026-04-15-analysis.md" | head -60
```

Expected: 새 섹션(`## Today's P&L`, `## Cumulative Return`, `## Max Drawdown`, `## Open Position Aging`) 포함 확인.

- [ ] **Step 6: Commit**

```bash
cd c:/Users/yjisu/Desktop/STOCK_WORK
git add scripts/daily_analysis.py
git commit -m "feat: daily_analysis — 누적수익률·MDD·포지션에이징·일간PnL 섹션 추가"
```

---

## Task 2: TMS AutoResearch → Obsidian 동기화 스크립트

**Files:**
- Create: `c:/Users/yjisu/Desktop/SCM_WORK/scripts/sync_tms_to_obsidian.py`

**동작 흐름:**
1. `git pull` (SCM_WORK 로컬 → 최신 GitHub Actions 결과 가져오기)
2. `_AutoResearch/SCM/outputs/week_*.md` 신규 파일 감지
3. `ClaudeVault/_AutoResearch/SCM/outputs/` 로 복사
4. `ClaudeVault/_AutoResearch/SCM/wiki/` 로 복사
5. 실행 로그 기록

- [ ] **Step 1: sync_tms_to_obsidian.py 생성**

```python
#!/usr/bin/env python3
"""TMS AutoResearch → Obsidian Vault 동기화 스크립트.

GitHub Actions가 매주 월요일 09:00 KST에 실행한 TMS 주간 분석 결과를
Obsidian Vault에 복사한다.

Usage:
    python scripts/sync_tms_to_obsidian.py          # git pull 포함
    python scripts/sync_tms_to_obsidian.py --no-pull # git pull 없이 복사만
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SCM_OUTPUTS = REPO_ROOT / "_AutoResearch" / "SCM" / "outputs"
SCM_WIKI    = REPO_ROOT / "_AutoResearch" / "SCM" / "wiki"

VAULT_ROOT   = Path(r"C:\Users\yjisu\Documents\ClaudeVault")
VAULT_OUTPUTS = VAULT_ROOT / "_AutoResearch" / "SCM" / "outputs"
VAULT_WIKI    = VAULT_ROOT / "_AutoResearch" / "SCM" / "wiki"

LOG_PATH = REPO_ROOT / "_AutoResearch" / "SCM" / "sync_log.txt"


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    line = f"[{ts}] {msg}"
    print(line)
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
    for src_file in src.glob("*.md"):
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
    parser = argparse.ArgumentParser(description="TMS AutoResearch → Obsidian 동기화")
    parser.add_argument("--no-pull", action="store_true", help="git pull 없이 복사만 수행")
    args = parser.parse_args()

    _log("=== TMS Obsidian 동기화 시작 ===")

    if not VAULT_ROOT.exists():
        _log(f"Obsidian Vault 없음: {VAULT_ROOT}. 종료.")
        sys.exit(1)

    if not args.no_pull:
        if not git_pull():
            _log("git pull 실패. --no-pull 로 재시도하거나 네트워크 확인 필요.")
            sys.exit(1)

    copied_outputs = sync_directory(SCM_OUTPUTS, VAULT_OUTPUTS)
    copied_wiki    = sync_directory(SCM_WIKI,    VAULT_WIKI)

    total = len(copied_outputs) + len(copied_wiki)
    if total == 0:
        _log("신규 파일 없음. 이미 최신 상태.")
    else:
        _log(f"=== 완료: outputs {len(copied_outputs)}개 + wiki {len(copied_wiki)}개 복사 ===")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 수동 테스트 실행**

```bash
cd c:/Users/yjisu/Desktop/SCM_WORK
python scripts/sync_tms_to_obsidian.py
```

Expected:
```
[2026-04-15 ...] === TMS Obsidian 동기화 시작 ===
[2026-04-15 ...] git pull 실행 중...
[2026-04-15 ...] git pull 완료: Already up to date.
[2026-04-15 ...] 복사: week_20260415.md → C:\...\ClaudeVault\_AutoResearch\SCM\outputs\week_20260415.md
[2026-04-15 ...] 복사: index.md → ...
[2026-04-15 ...] === 완료: outputs 1개 + wiki 2개 복사 ===
```

- [ ] **Step 3: Obsidian vault에서 파일 확인**

```bash
ls "c:/Users/yjisu/Documents/ClaudeVault/_AutoResearch/SCM/outputs/"
ls "c:/Users/yjisu/Documents/ClaudeVault/_AutoResearch/SCM/wiki/"
```

Expected: `week_20260415.md`, `index.md`, `log.md` 존재 확인.

- [ ] **Step 4: Windows 작업 스케줄러 등록**

PowerShell에서 실행 (관리자 권한 불필요):

```powershell
$pythonPath = (python -c "import sys; print(sys.executable)")
$scriptPath = "c:\Users\yjisu\Desktop\SCM_WORK\scripts\sync_tms_to_obsidian.py"

$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument $scriptPath `
    -WorkingDirectory "c:\Users\yjisu\Desktop\SCM_WORK"

# 매주 월요일 09:15 KST (GitHub Actions 09:00 완료 후 15분 여유)
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "09:15"

$settings = New-ScheduledTaskSettingsSet `
    -RunOnlyIfNetworkAvailable `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName "TMS-AutoResearch-Obsidian-Sync" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "TMS 주간 AutoResearch 결과를 Obsidian Vault로 동기화" `
    -Force
```

확인:
```powershell
Get-ScheduledTask -TaskName "TMS-AutoResearch-Obsidian-Sync" | Format-List
```

- [ ] **Step 5: Commit (SCM_WORK)**

```bash
cd c:/Users/yjisu/Desktop/SCM_WORK
git add scripts/sync_tms_to_obsidian.py
git commit -m "feat: TMS AutoResearch → Obsidian 동기화 스크립트 추가"
```

---

## Task 3: Antigravity 프로젝트 분리 + CLAUDE.md/Skills 독립성

**코드 변경 없음 — 설정 확인 및 사용 방법 가이드**

### 프로젝트별 독립성 현황 (이미 완성)

| 항목 | SCM_WORK | STOCK_WORK | 공유 여부 |
|------|----------|------------|---------|
| `CLAUDE.md` | `SCM_WORK/CLAUDE.md` | `STOCK_WORK/CLAUDE.md` | 프로젝트별 독립 ✅ |
| `.claude/agents/` | 14개 도메인 에이전트 | 10개 거래 에이전트 | 프로젝트별 독립 ✅ |
| `.claude/skills/` | 10개 SCM/회계/기술 스킬 | 4개 트레이딩 스킬 | 프로젝트별 독립 ✅ |
| `.claude/commands/` | 15개 커맨드 | 1개 커맨드 | 프로젝트별 독립 ✅ |
| `.claude/hooks/` | 8개 훅 | 2개 훅 | 프로젝트별 독립 ✅ |
| `~/.claude/CLAUDE.md` | 공유 전역 지침 | 공유 전역 지침 | 전역 공유 (의도됨) |
| `~/.claude/skills/` | graphify 등 공통 스킬 | graphify 등 공통 스킬 | 전역 공유 (의도됨) |

### Antigravity에서 창 분리하는 방법

- [ ] **Step 1: SCM_WORK 전용 창 열기**

Antigravity 메뉴: `File → Open Folder` → `C:\Users\yjisu\Desktop\SCM_WORK` 선택

- [ ] **Step 2: STOCK_WORK 전용 창 열기**

`File → New Window` (또는 `Ctrl+Shift+N`) → `File → Open Folder` → `C:\Users\yjisu\Desktop\STOCK_WORK`

**결과:** 각 창이 독립된 Claude Code 컨텍스트를 가짐
- 창 1(SCM_WORK): SCM 14개 에이전트 + SCM CLAUDE.md + 물류/회계 스킬
- 창 2(STOCK_WORK): 거래 10개 에이전트 + STOCK CLAUDE.md + 트레이딩 스킬
- AI 컨텍스트 혼용 없음 ✅

---

## 검증 체크리스트

- [ ] STOCK 리포트: `reports/daily/YYYY-MM-DD-analysis.md` 에 4개 신규 섹션 포함
- [ ] STOCK Obsidian: `ClaudeVault/STOCK/DailyReport/` 에 자동 복사 확인
- [ ] TMS 스크립트: `ClaudeVault/_AutoResearch/SCM/outputs/week_*.md` 복사 확인
- [ ] 작업 스케줄러: `Get-ScheduledTask -TaskName "TMS-AutoResearch-Obsidian-Sync"` 등록 확인
- [ ] Antigravity: 두 창 독립적으로 열리고 각자 프로젝트 컨텍스트 인식 확인
