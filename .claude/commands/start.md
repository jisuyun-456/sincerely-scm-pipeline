# /start — 세션 시작 루틴

세션 시작 시 아래 순서대로 실행하세요.

## 1. 이전 세션 확인
```bash
cat .claude/claude-progress.txt
```

## 2. 미완료 태스크 출력 (priority 순)
```bash
python3 -c "
import json, os
path = os.path.join('.claude', 'feature_list.json')
with open(path, encoding='utf-8') as f:
    tasks = json.load(f)
todo = [t for t in tasks if not t['passes']]
order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
todo.sort(key=lambda x: order.get(x['priority'], 9))
for t in todo:
    print(f\"[{t['priority']:8s}] {t['domain']:20s} | {t['task']}\")
print(f'\n총 {len(todo)}건 미완료 / {len(tasks)}건 전체')
"
```

## 3. 최근 git 히스토리
```bash
git log --oneline -10
```

## 4. 다음 작업 제안
위 결과를 종합하여 **다음에 작업할 태스크 1개**를 제안하세요.
선정 기준:
1. priority: critical > high > medium > low
2. 같은 우선순위면 이전 세션 작업과 연관된 태스크 우선
3. 한 번에 하나의 태스크만 시작
