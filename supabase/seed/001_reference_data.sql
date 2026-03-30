-- =============================================================================
-- Seed 001: Reference Data — UoM, GL Accounts, Material Types, Material Groups, Cost Settings
-- =============================================================================

-- ---------------------------------------------------------------------------
-- shared.units_of_measure
-- ---------------------------------------------------------------------------
INSERT INTO shared.units_of_measure (uom_code, uom_name, dimension) VALUES
('EA', '개', 'quantity'),
('SET', '세트', 'quantity'),
('BOX', '박스', 'quantity'),
('PCS', '피스', 'quantity'),
('M', '미터', 'length'),
('KG', '킬로그램', 'weight'),
('ROLL', '롤', 'quantity'),
('SHEET', '매', 'quantity'),
('PACK', '팩', 'quantity');

-- ---------------------------------------------------------------------------
-- shared.gl_accounts
-- ---------------------------------------------------------------------------

-- 자산 계정 (재고자산)
INSERT INTO shared.gl_accounts (id, account_code, account_name, account_type, ifrs_category, normal_balance, douzone_code) VALUES
('aaaaaaaa-gl01-0000-0000-000000000001', '146000', '원재료', 'asset', 'inventory', 'debit', '146000'),
('aaaaaaaa-gl02-0000-0000-000000000002', '147000', '재공품', 'asset', 'inventory', 'debit', '147000'),
('aaaaaaaa-gl03-0000-0000-000000000003', '150000', '제품', 'asset', 'inventory', 'debit', '150000'),
('aaaaaaaa-gl04-0000-0000-000000000004', '153000', '상품', 'asset', 'inventory', 'debit', '153000'),
('aaaaaaaa-gl05-0000-0000-000000000005', '155000', '소모품', 'asset', 'inventory', 'debit', '155000');

-- 부채 계정
INSERT INTO shared.gl_accounts (id, account_code, account_name, account_type, ifrs_category, normal_balance, douzone_code) VALUES
('aaaaaaaa-gl06-0000-0000-000000000006', '251000', '매입채무', 'liability', 'trade_payable', 'credit', '251000'),
('aaaaaaaa-gl07-0000-0000-000000000007', '253000', '미지급금', 'liability', 'other_payable', 'credit', '253000'),
('aaaaaaaa-gl08-0000-0000-000000000008', '255000', '선수금', 'liability', 'advance_receipt', 'credit', '255000');

-- 수익 계정
INSERT INTO shared.gl_accounts (id, account_code, account_name, account_type, ifrs_category, normal_balance, douzone_code) VALUES
('aaaaaaaa-gl09-0000-0000-000000000009', '401000', '매출', 'revenue', 'revenue', 'credit', '401000'),
('aaaaaaaa-gl10-0000-0000-000000000010', '909000', '잡이익', 'revenue', 'other', 'credit', '909000');

-- 비용 계정
INSERT INTO shared.gl_accounts (id, account_code, account_name, account_type, ifrs_category, normal_balance, douzone_code) VALUES
('aaaaaaaa-gl11-0000-0000-000000000011', '501000', '매출원가', 'expense', 'cogs', 'debit', '501000'),
('aaaaaaaa-gl12-0000-0000-000000000012', '820000', '임가공비', 'expense', 'cogs', 'debit', '820000'),
('aaaaaaaa-gl13-0000-0000-000000000013', '831000', '운반비(매출)', 'expense', 'freight', 'debit', '831000'),
('aaaaaaaa-gl14-0000-0000-000000000014', '840000', '운반비(비용)', 'expense', 'freight', 'debit', '840000'),
('aaaaaaaa-gl15-0000-0000-000000000015', '909100', '잡손실', 'expense', 'other', 'debit', '909100');

-- ---------------------------------------------------------------------------
-- shared.material_types (NEW — automatic account determination per FIX-4)
-- ---------------------------------------------------------------------------
INSERT INTO shared.material_types (id, type_code, type_name, is_stockable, is_batch_managed, default_procurement, default_valuation_class,
  default_debit_gl_id, default_credit_gl_id, issue_debit_gl_id, issue_credit_gl_id) VALUES
-- ROH: 원재료 — GR: DR 원재료(146000) / CR 매입채무(251000); GI: DR 매출원가(501000) / CR 원재료(146000)
('bbbbbbbb-mt01-0000-0000-000000000001', 'ROH', '원재료', TRUE, FALSE, 'F', '3000',
  'aaaaaaaa-gl01-0000-0000-000000000001', 'aaaaaaaa-gl06-0000-0000-000000000006',
  'aaaaaaaa-gl11-0000-0000-000000000011', 'aaaaaaaa-gl01-0000-0000-000000000001'),
-- HALB: 반제품 — GR: DR 재공품(147000) / CR 매입채무(251000); GI: DR 매출원가(501000) / CR 재공품(147000)
('bbbbbbbb-mt02-0000-0000-000000000002', 'HALB', '반제품(아이템)', TRUE, FALSE, 'X', '7900',
  'aaaaaaaa-gl02-0000-0000-000000000002', 'aaaaaaaa-gl06-0000-0000-000000000006',
  'aaaaaaaa-gl11-0000-0000-000000000011', 'aaaaaaaa-gl02-0000-0000-000000000002'),
-- FERT: 완제품 — GR: DR 제품(150000) / CR 재공품(147000); GI: DR 매출원가(501000) / CR 제품(150000)
('bbbbbbbb-mt03-0000-0000-000000000003', 'FERT', '완제품(굿즈)', TRUE, FALSE, 'E', '7920',
  'aaaaaaaa-gl03-0000-0000-000000000003', 'aaaaaaaa-gl02-0000-0000-000000000002',
  'aaaaaaaa-gl11-0000-0000-000000000011', 'aaaaaaaa-gl03-0000-0000-000000000003'),
-- VERP: 포장재 — GR: DR 원재료(146000) / CR 매입채무(251000); GI: DR 매출원가(501000) / CR 원재료(146000)
('bbbbbbbb-mt04-0000-0000-000000000004', 'VERP', '포장재', TRUE, FALSE, 'F', '3001',
  'aaaaaaaa-gl01-0000-0000-000000000001', 'aaaaaaaa-gl06-0000-0000-000000000006',
  'aaaaaaaa-gl11-0000-0000-000000000011', 'aaaaaaaa-gl01-0000-0000-000000000001'),
-- HAWA: 상품 — GR: DR 상품(153000) / CR 매입채무(251000); GI: DR 매출원가(501000) / CR 상품(153000)
('bbbbbbbb-mt05-0000-0000-000000000005', 'HAWA', '상품(머천다이즈)', TRUE, FALSE, 'F', '3100',
  'aaaaaaaa-gl04-0000-0000-000000000004', 'aaaaaaaa-gl06-0000-0000-000000000006',
  'aaaaaaaa-gl11-0000-0000-000000000011', 'aaaaaaaa-gl04-0000-0000-000000000004'),
-- HIBE: 소모품 — GR: DR 소모품(155000) / CR 매입채무(251000); GI: DR 비용 / CR 소모품
('bbbbbbbb-mt06-0000-0000-000000000006', 'HIBE', '소모품', TRUE, FALSE, 'F', '3200',
  'aaaaaaaa-gl05-0000-0000-000000000005', 'aaaaaaaa-gl06-0000-0000-000000000006',
  'aaaaaaaa-gl14-0000-0000-000000000014', 'aaaaaaaa-gl05-0000-0000-000000000005');

-- ---------------------------------------------------------------------------
-- shared.material_groups (NEW)
-- ---------------------------------------------------------------------------
INSERT INTO shared.material_groups (id, group_code, group_name) VALUES
('cccccccc-mg01-0000-0000-000000000001', 'MG-TUMBLER', '텀블러/보온병'),
('cccccccc-mg02-0000-0000-000000000002', 'MG-STATIONERY', '문구류'),
('cccccccc-mg03-0000-0000-000000000003', 'MG-PACKAGING', '포장재'),
('cccccccc-mg04-0000-0000-000000000004', 'MG-ELECTRONICS', '전자기기'),
('cccccccc-mg05-0000-0000-000000000005', 'MG-MERCH', '머천다이즈/기념품'),
('cccccccc-mg06-0000-0000-000000000006', 'MG-TEXTILE', '의류/섬유'),
('cccccccc-mg07-0000-0000-000000000007', 'MG-ETC', '기타');

-- ---------------------------------------------------------------------------
-- finance.cost_settings
-- ---------------------------------------------------------------------------
INSERT INTO finance.cost_settings (parts_type, costing_method, effective_from) VALUES
('raw', 'weighted_avg', '2026-01-01'),
('packaging', 'weighted_avg', '2026-01-01'),
('merchandise', 'weighted_avg', '2026-01-01'),
('semi_finished', 'weighted_avg', '2026-01-01');
