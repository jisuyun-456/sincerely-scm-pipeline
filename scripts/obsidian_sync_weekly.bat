@echo off
:: 매주 월요일 10:00 KST — Windows 작업 스케줄러에서 자동 실행
:: GitHub Actions가 08:30에 분석을 push하고, 이 스크립트가 git pull 후 Obsidian에 복사

cd /d C:\Users\yjisu\Desktop\SCM_WORK

echo [%DATE% %TIME%] git pull 최신 데이터 수신...
git pull origin main

echo [%DATE% %TIME%] TMS Obsidian 동기화 시작...
python scripts/sync_tms_to_obsidian.py

echo [%DATE% %TIME%] WMS Obsidian 동기화 시작...
python scripts/sync_wms_to_obsidian.py

echo [%DATE% %TIME%] graphify 지식 그래프 → ClaudeVault 동기화...
if exist graphify-out\obsidian (
    xcopy /E /I /Y graphify-out\obsidian\* "C:\Users\yjisu\Documents\ClaudeVault\SCM\graphify\"
    echo [%DATE% %TIME%] graphify vault 동기화 완료.
) else (
    echo [%DATE% %TIME%] graphify-out\obsidian 없음 — 건너뜀.
)

echo [%DATE% %TIME%] 전체 동기화 완료.
