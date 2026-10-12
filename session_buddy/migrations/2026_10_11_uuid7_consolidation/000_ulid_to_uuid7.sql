-- 000_ulid_to_uuid7.sql
-- Registers the deterministic UUID7 UDF used by 001-007.
-- Run BEFORE any consolidation step. Idempotent (CREATE OR REPLACE).
CREATE OR REPLACE FUNCTION ulid_to_uuid7(ulid_text VARCHAR) RETURNS VARCHAR
LANGUAGE python
AS $$
from session_buddy.migrations.udf import ulid_to_uuid7
return ulid_to_uuid7(ulid_text)
$$;
