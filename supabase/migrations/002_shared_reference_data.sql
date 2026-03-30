-- ============================================================
-- Migration 002: shared Schema — Reference/Config Tables
-- SAP: T134 (Material Types), T023 (Material Groups),
--       T006 (Units of Measure), SKA1 (Chart of Accounts)
-- 이 테이블들은 다른 모든 테이블에서 참조되므로 가장 먼저 생성
-- ============================================================

-- -------------------------------------------------------
-- shared.units_of_measure (SAP T006)
-- 모든 수량 필드에서 참조하는 단위 마스터
-- -------------------------------------------------------
CREATE TABLE shared.units_of_measure (
  uom_code   VARCHAR(10) PRIMARY KEY,  -- EA, M, KG, SET, BOX, SHEET, ROLL, PCS
  uom_name   VARCHAR(50) NOT NULL,
  dimension  VARCHAR(20),  -- quantity, length, weight, volume, area
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- -------------------------------------------------------
-- shared.gl_accounts (SAP: Chart of Accounts — 더존 코드 매핑)
-- -------------------------------------------------------
CREATE TABLE shared.gl_accounts (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_code   VARCHAR(10) UNIQUE NOT NULL,   -- 더존 계정코드 (예: 146000)
  account_name   VARCHAR(100) NOT NULL,          -- 원재료, 제품, 매출원가 등
  account_type   VARCHAR(20) NOT NULL,           -- asset, liability, equity, revenue, expense
  ifrs_category  VARCHAR(30),                    -- inventory, cogs, trade_payable, trade_receivable
  normal_balance VARCHAR(6) NOT NULL,            -- debit, credit
  parent_id      UUID REFERENCES shared.gl_accounts(id),
  douzone_code   VARCHAR(20),                    -- 더존 아마란스10 내부 코드
  is_active      BOOLEAN DEFAULT TRUE,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- -------------------------------------------------------
-- shared.material_types (SAP T134)
-- 자재유형 — GL 계정 자동결정의 핵심 참조 테이블
-- -------------------------------------------------------
CREATE TABLE shared.material_types (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type_code               VARCHAR(10) UNIQUE NOT NULL,  -- ROH, HALB, FERT, VERP, HIBE, HAWA
  type_name               VARCHAR(100) NOT NULL,
  is_stockable            BOOLEAN DEFAULT TRUE,
  is_batch_managed        BOOLEAN DEFAULT FALSE,
  default_procurement     VARCHAR(1),  -- E(in-house), F(external), X(both)
  default_valuation_class VARCHAR(10),
  -- GL 계정 자동결정 (FIX-4: 하드코딩 제거)
  default_debit_gl_id     UUID REFERENCES shared.gl_accounts(id),  -- GR 시 차변 계정
  default_credit_gl_id    UUID REFERENCES shared.gl_accounts(id),  -- GR 시 대변 계정
  issue_debit_gl_id       UUID REFERENCES shared.gl_accounts(id),  -- GI 시 차변 (매출원가 등)
  issue_credit_gl_id      UUID REFERENCES shared.gl_accounts(id),  -- GI 시 대변 (재고자산)
  created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- -------------------------------------------------------
-- shared.material_groups (SAP T023)
-- 자재그룹 — 구매분석, 지출분석용 분류
-- -------------------------------------------------------
CREATE TABLE shared.material_groups (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  group_code VARCHAR(20) UNIQUE NOT NULL,
  group_name VARCHAR(100) NOT NULL,
  parent_id  UUID REFERENCES shared.material_groups(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);
