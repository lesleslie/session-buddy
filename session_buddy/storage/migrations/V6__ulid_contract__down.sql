-- ULID Contract Rollback: Restore legacy IDs from backup
-- This restores the state before contract migration

-- Conversations table rollback
ALTER TABLE conversations RENAME COLUMN id TO conversation_ulid;
ALTER TABLE conversations ADD COLUMN id TEXT;
UPDATE conversations SET id = conversation_ulid;
ALTER TABLE conversations ALTER COLUMN id ADD PRIMARY KEY;
ALTER TABLE conversations DROP COLUMN conversation_ulid;
ALTER TABLE conversations ADD COLUMN conversation_ulid_generated_at TIMESTAMP;

-- Reflections table rollback
ALTER TABLE reflections RENAME COLUMN id TO reflection_ulid;
ALTER TABLE reflections ADD COLUMN id TEXT;
UPDATE reflections SET id = reflection_ulid;
ALTER TABLE reflections ALTER COLUMN id ADD PRIMARY KEY;
ALTER TABLE reflections DROP COLUMN reflection_ulid;
ALTER TABLE reflections ADD COLUMN reflection_ulid_generated_at TIMESTAMP;

-- Code graphs table rollback
ALTER TABLE code_graphs RENAME COLUMN id TO code_graph_ulid;
ALTER TABLE code_graphs ADD COLUMN id TEXT;
UPDATE code_graphs SET id = code_graph_ulid;
ALTER TABLE code_graphs ALTER COLUMN id ADD PRIMARY KEY;
ALTER TABLE code_graphs DROP COLUMN code_graph_ulid;
ALTER TABLE code_graphs ADD COLUMN code_graph_ulid_generated_at TIMESTAMP;
