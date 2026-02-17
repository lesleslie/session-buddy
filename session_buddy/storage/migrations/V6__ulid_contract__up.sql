-- ULID Contract Migration: Drop legacy IDs, make ULIDs primary
-- This is the CONTRACT phase of expand-contract migration
-- After this migration, all foreign keys and indexes should use ULID

-- Conversations table: Drop legacy id, make conversation_ulid primary
-- Step 1: Migrate any remaining NULL conversation_ulid values
UPDATE conversations SET conversation_ulid = 'fallback_' || substr(hex(randomblob(16)), 1, 26) WHERE conversation_ulid IS NULL;

-- Step 2: Make conversation_ulid NOT NULL
ALTER TABLE conversations ALTER COLUMN conversation_ulid SET NOT NULL;

-- Step 3: Drop legacy id column
ALTER TABLE conversations DROP COLUMN id;

-- Step 4: Rename conversation_ulid to id (become primary identifier)
ALTER TABLE conversations ALTER COLUMN conversation_ulid RENAME TO id;

-- Step 5: Make id PRIMARY KEY
ALTER TABLE conversations ALTER COLUMN id ADD PRIMARY KEY;

-- Step 6: Drop timestamp column
ALTER TABLE conversations DROP COLUMN conversation_ulid_generated_at;

-- Reflections table: Apply same changes
UPDATE reflections SET reflection_ulid = 'fallback_' || substr(hex(randomblob(16)), 1, 26) WHERE reflection_ulid IS NULL;
ALTER TABLE reflections ALTER COLUMN reflection_ulid SET NOT NULL;
ALTER TABLE reflections DROP COLUMN id;
ALTER TABLE reflections ALTER COLUMN reflection_ulid RENAME TO id;
ALTER TABLE reflections ALTER COLUMN id ADD PRIMARY KEY;
ALTER TABLE reflections DROP COLUMN reflection_ulid_generated_at;

-- Code graphs table: Apply same changes
UPDATE code_graphs SET code_graph_ulid = 'fallback_' || substr(hex(randomblob(16)), 1, 26) WHERE code_graph_ulid IS NULL;
ALTER TABLE code_graphs ALTER COLUMN code_graph_ulid SET NOT NULL;
ALTER TABLE code_graphs DROP COLUMN id;
ALTER TABLE code_graphs ALTER COLUMN code_graph_ulid RENAME TO id;
ALTER TABLE code_graphs ALTER COLUMN id ADD PRIMARY KEY;
ALTER TABLE code_graphs DROP COLUMN code_graph_ulid_generated_at;
