CREATE TABLE IF NOT EXISTS pipeline_runs (
    id                   UUID PRIMARY KEY,
    mission_id           UUID NOT NULL REFERENCES missions(id),
    temporal_workflow_id TEXT NOT NULL UNIQUE,
    preset               TEXT NOT NULL DEFAULT 'standard',
    started_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_mission_id ON pipeline_runs(mission_id);
