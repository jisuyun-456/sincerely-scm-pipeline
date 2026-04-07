워크트리를 사용해 독립된 작업 공간을 생성한다. `superpowers:using-git-worktrees` 스킬을 즉시 호출하여 실행하라.

## SCM_WORK 기본 설정

- 워크트리 기본 경로: `c:\Users\yjisu\Desktop\SCM_WORK\.worktrees\`
- 브랜치 명명 규칙: `feature/<기능명>`, `fix/<버그명>`, `refactor/<대상>`
- 워크트리는 `.gitignore`에 등록되어야 함 (커밋 대상 아님)

## 실행 흐름

1. `superpowers:using-git-worktrees` 스킬 호출
2. 스킬 지침에 따라 `.worktrees/` 존재 여부 확인 후 워크트리 생성
3. 생성된 워크트리 경로와 브랜치명을 사용자에게 보고
4. 새 터미널에서 해당 경로로 `claude` 실행 안내

## 병렬 작업 예시

```
터미널1: cd .worktrees/feature-wms-outbound && claude
터미널2: cd .worktrees/fix-otif-calc && claude
터미널3: (메인) — 병합 및 리뷰 담당
```