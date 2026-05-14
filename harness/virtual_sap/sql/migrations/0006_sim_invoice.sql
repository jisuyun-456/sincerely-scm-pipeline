-- Migration 0006: Sales Invoices
-- Populated by invoice_agent after fi_document doc_type='SD' is posted.

CREATE TABLE IF NOT EXISTS sap.sim_invoice (
    invoice_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fi_doc_id       TEXT NOT NULL REFERENCES sap.fi_document(fi_doc_id),
    so_id           TEXT REFERENCES sap.sales_order(so_id),
    customer_id     TEXT REFERENCES sap.business_partner(bp_id),
    amount          NUMERIC(14,2) NOT NULL DEFAULT 0,   -- 공급가액 (KRW)
    tax_amount      NUMERIC(14,2) NOT NULL DEFAULT 0,   -- VAT 10%
    total_amount    NUMERIC(14,2) NOT NULL DEFAULT 0,   -- 합계금액
    status          TEXT NOT NULL DEFAULT 'issued' CHECK (status IN ('issued','sent','paid','cancelled')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS sim_invoice_fi_doc_id_idx  ON sap.sim_invoice (fi_doc_id);
CREATE INDEX IF NOT EXISTS sim_invoice_so_id_idx      ON sap.sim_invoice (so_id);
CREATE INDEX IF NOT EXISTS sim_invoice_customer_id_idx ON sap.sim_invoice (customer_id);
