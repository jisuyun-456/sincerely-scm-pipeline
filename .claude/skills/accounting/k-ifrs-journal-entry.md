# K-IFRS 분개 처리 방법론

## 재고 이동별 분개 (016_triggers_finance.sql 기반)

### 입고 (101, Goods Receipt)
```
차) 재고자산 (material_type.default_debit_gl)    XXX
대) 매입채무 (material_type.default_credit_gl)   XXX
```

### 비용출고 (201, Issue to Cost Center)
```
차) 비용계정 (material_type.issue_debit_gl)      XXX
대) 재고자산 (material_type.issue_credit_gl)      XXX
```

### 생산출고 (261, GI for Assembly)
```
차) 재공품/생산비용                               XXX
대) 재고자산                                      XXX
```

### 생산입고 (262, GR from Assembly)
```
차) 재고자산                                      XXX
대) 재공품/생산비용                               XXX
```

### 고객납품 (601, Goods Issue for Delivery)
```
차) 매출원가 (5110)                              XXX
대) 재고자산 (1140)                              XXX
```

### 운송비 (Freight Order)
```
차) 운반비 (831000)                              XXX
대) 미지급금 (253000)                            XXX
```

### 재고조정
```
과잉 발견:
  차) 재고자산                                    XXX
  대) 잡이익 (909000)                            XXX

부족 발견:
  차) 잡손실 (909100)                            XXX
  대) 재고자산                                    XXX
```

## 더존 아마란스10 계정코드 체계

```
1xxx: 자산    (1140 재고자산, 1141 재고자산평가충당금)
2xxx: 부채    (2110 매입채무, 253000 미지급금)
3xxx: 자본
4xxx: 수익    (909000 잡이익)
5xxx: 비용    (5110 매출원가, 5210 재고평가손실, 909100 잡손실)
8xxx: 판관비  (831000 운반비)
```

## GL 계정 자동 결정 (material_type 기반)

016_triggers_finance.sql의 핵심 설계:
- GL 계정은 하드코딩하지 않음
- shared.material_types 테이블의 4개 GL 필드로 동적 결정:
  - default_debit_gl_id (입고 차변)
  - default_credit_gl_id (입고 대변)
  - issue_debit_gl_id (출고 차변)
  - issue_credit_gl_id (출고 대변)

## 전표번호 형식
AE-YYYYMMDD-NNNN (일별 순번, advisory lock으로 동시성 제어)

## 전표 상태 워크플로우
draft → reviewed → posted (더존 전표번호 매핑 후)
posted 시 douzone_slip_no 기록

## 기간 마감 (period_close)
- 마감된 기간에는 전표 INSERT 차단
- 마감 해제: period_close.is_closed = false로 UPDATE (백필 시 사용)

## 현재 상태
- finance 스키마(011) + 트리거(016) 설계 완료
- 실제 운영 DB(sap 스키마)에는 미적용
- NestJS에서의 K-IFRS 분개 자동생성 로직 미구현
