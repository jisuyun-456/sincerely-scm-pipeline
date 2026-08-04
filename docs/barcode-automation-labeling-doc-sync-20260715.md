# Barcode 베이스 — 라벨링작업 → 문서출력 자동 복사 (2026-07-15)

Airtable Automation은 REST API로 편집할 수 없어 Airtable UI에서 수동으로 적용해야 한다. 이 문서는 원본 스크립트 백업(롤백용) + 적용할 변경사항 런북이다.

## 대상 베이스

Barcode (`app4LvuNIDiqTmhnv`) — 피킹리스트(`tbl1AH1EmMSbhik0H`) / 라벨링작업(`tblnxU0PlegXT7bYj`) / 문서출력(`tblMQG1PYioIUWdbe`)

## 백업 — 편집 전 원본 스크립트

### 자동화 ① "테스트 results" (라벨링작업 테이블, 월 72회 실행) — 원본

```js
let pickingListTable = base.getTable("피킹리스트");
let movingListTable = base.getTable("라벨링작업");

// 특정 뷰에서만 데이터 가져오기
let pickingListQuery = await pickingListTable.selectRecordsAsync({
    fields: ["project", "라벨링작업"],
    view: "(기능) 이동리스트_피킹리스트 연결_지수" // 올바른 뷰 이름 적용
});
let pickingListRecords = pickingListQuery.records;

let movingListQuery = await movingListTable.selectRecordsAsync({ fields: ["project", "출하장소"] });
let movingListRecords = movingListQuery.records;

// 피킹리스트와 이동리스트 간의 연결 설정
for (let pickingRecord of pickingListRecords) {
    let projectName = pickingRecord.getCellValue("project");

    let matchingRecords = movingListRecords.filter(record => {
        let projectNames = record.getCellValue("project") || [];
        return projectNames.includes(projectName);
    });

    let linkedRecords = matchingRecords.map(record => ({ id: record.id }));

    await pickingListTable.updateRecordAsync(pickingRecord.id, {
        "라벨링작업": linkedRecords
    });
}
```

### 자동화 ② (피킹리스트 테이블, "When a record is created", 월 4회 실행) — 원본 "Run a script" 스텝

```js
const { triggerRecordId, newDocRecordId } = input.config();

const pickingTable = base.getTable('피킹리스트');
const docTable     = base.getTable('문서출력');

// 피킹리스트 레코드에서 라벨링작업 linked IDs 가져오기
const pickingRecord = await pickingTable.selectRecordAsync(triggerRecordId, {
    fields: ['라벨링작업']
});

const labelingWork = pickingRecord.getCellValue('라벨링작업');

if (labelingWork && labelingWork.length > 0) {
    await docTable.updateRecordAsync(newDocRecordId, {
        '라벨링작업': labelingWork // linked record 배열 그대로 전달
    });
    output.set('result', `linked ${labelingWork.length} MM codes`);
} else {
    output.set('result', 'no labeling work at creation time');
}
```

이 스텝 앞에 있는 "Create record" 액션(문서출력 테이블, `피킹리스트 2` = Airtable record ID)은 **그대로 유지**. 위 "Run a script" 스텝만 삭제 대상.

## 왜 바꾸는가

피킹리스트 레코드가 **생성되는 시점**엔 `라벨링작업` 필드가 거의 항상 비어 있다 — 그 필드는 자동화 ①이 나중에(라벨링작업 레코드가 특정 뷰에 들어올 때) 비동기로 채운다. 그래서 자동화 ②의 복사 스크립트는 실전에서 대부분 `else` 분기만 타는 죽은 코드였다. 스크린샷의 `Could not find a record with ID 'rec9OlsKpiHf53aA6'` 에러는 Create record 스텝을 "Generate a preview"로만 테스트해서 생긴 가짜(미저장) 레코드 ID를 스크립트 테스트가 참조했기 때문으로 보인다.

Airtable Meta API로 스키마를 확인한 결과, 아래 연결고리가 이미 존재해서 자동화 ①에서 바로 동기화할 수 있다:
- 피킹리스트.`문서출력` (`fldciK63huKpNKPbJ`) — 문서출력.`피킹리스트 2`의 대칭 역링크. 자동화 ②의 Create record 액션이 레코드 생성 시 이미 채워준다.
- 문서출력.`라벨링작업` (`fldbPHrVcBrUr39R3`) — 쓰기 가능한 정상 링크 필드.

## 적용할 변경

### 1. 자동화 ① "테스트 results" 스크립트를 아래로 교체

```js
let pickingListTable = base.getTable("피킹리스트");
let movingListTable = base.getTable("라벨링작업");
let docTable = base.getTable("문서출력");

// 특정 뷰에서만 데이터 가져오기
let pickingListQuery = await pickingListTable.selectRecordsAsync({
    fields: ["project", "라벨링작업", "문서출력"],
    view: "(기능) 이동리스트_피킹리스트 연결_지수" // 올바른 뷰 이름 적용
});
let pickingListRecords = pickingListQuery.records;

let movingListQuery = await movingListTable.selectRecordsAsync({ fields: ["project", "출하장소"] });
let movingListRecords = movingListQuery.records;

// 피킹리스트와 이동리스트 간의 연결 설정
for (let pickingRecord of pickingListRecords) {
    let projectName = pickingRecord.getCellValue("project");

    let matchingRecords = movingListRecords.filter(record => {
        let projectNames = record.getCellValue("project") || [];
        return projectNames.includes(projectName);
    });

    let linkedRecords = matchingRecords.map(record => ({ id: record.id }));

    await pickingListTable.updateRecordAsync(pickingRecord.id, {
        "라벨링작업": linkedRecords
    });

    // 문서출력에도 동일한 라벨링작업 링크를 즉시 복사
    let linkedDocs = pickingRecord.getCellValue("문서출력") || [];
    for (let doc of linkedDocs) {
        await docTable.updateRecordAsync(doc.id, {
            "라벨링작업": linkedRecords
        });
    }
}
```

변경점: `docTable` 선언 추가, `pickingListQuery.fields`에 `"문서출력"` 추가, 루프 안에 문서출력 동기화 블록 추가. 나머지는 원본과 동일.

### 2. 자동화 ②에서 "Run a script" 스텝 삭제

Create record 액션은 유지, 그 뒤의 스크립트 스텝만 제거.

## 검증

1. 변경 1 저장 후 "Test" (전체 자동화 테스트, 스텝 단독 preview 아님)를 `라벨링작업` + `문서출력`이 이미 채워진 실제 레코드로 실행 → 에러 없이 끝나고 대상 문서출력 레코드의 `라벨링작업`이 채워지는지 Data 탭에서 확인.
2. 라벨링작업 레코드를 새로 만들어 뷰 `(기능) 이동리스트_피킹리스트 연결_지수`에 진입시킨 뒤, 해당 project의 피킹리스트·문서출력 레코드 양쪽에 같은 MM 코드가 링크되는지 확인.
3. 변경 2 이후 신규 피킹리스트 레코드 생성 시 문서출력 레코드가 여전히 정상 생성되는지 확인.
4. Automation 실행 History에서 "Step successful"로 끝나는지 확인.
