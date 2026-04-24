CREATE TABLE IF NOT EXISTS admin_notes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  entity_type text NOT NULL CHECK (entity_type IN ('query_log', 'mapping_upload')),
  entity_id   uuid NOT NULL,
  note        text NOT NULL,
  created_by  text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_admin_notes_entity ON admin_notes (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_admin_notes_project ON admin_notes (project_id);
