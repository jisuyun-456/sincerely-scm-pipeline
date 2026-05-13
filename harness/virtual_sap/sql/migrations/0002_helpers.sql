-- Helper function for sequential document number generation
-- Called by harness/virtual_sap/id_gen.py via supabase_client.rpc()

CREATE OR REPLACE FUNCTION sap.vsap_next_seq(p_prefix TEXT, p_period TEXT)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_seq INT;
BEGIN
    INSERT INTO sap.doc_counter (prefix, period, last_seq)
    VALUES (p_prefix, p_period, 1)
    ON CONFLICT (prefix, period)
    DO UPDATE SET last_seq = sap.doc_counter.last_seq + 1
    RETURNING last_seq INTO v_seq;
    RETURN v_seq;
END;
$$;
