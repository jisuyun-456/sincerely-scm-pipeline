-- ============================================================
-- Migration 001: Schema Namespace 생성
-- SAP S/4HANA Full Enterprise 기반 6개 Schema
-- Version: v4 (2026-03-29 완전 재작성)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS shared;   -- SAP: Master Data (MM/BP/PS)
CREATE SCHEMA IF NOT EXISTS tms;      -- SAP: TM (Transportation Management)
CREATE SCHEMA IF NOT EXISTS wms;      -- SAP: EWM (Extended Warehouse Management)
CREATE SCHEMA IF NOT EXISTS mm;       -- SAP: MM (Materials Management) + QM
CREATE SCHEMA IF NOT EXISTS pp;       -- SAP: PP (Production Planning)
CREATE SCHEMA IF NOT EXISTS finance;  -- SAP: FI 경량화 + 더존 아마란스10 연계

-- cross-schema FK를 위한 search_path 설정
ALTER DATABASE postgres SET search_path TO shared, tms, wms, mm, pp, finance, public;
