BEGIN;

CREATE TABLE missions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text NOT NULL,
    classification  text NOT NULL CHECK (classification IN ('unclassified','confidential','restricted')),
    aoi             geography(Polygon, 4326) NOT NULL,
    status          text NOT NULL DEFAULT 'created'
                    CHECK (status IN ('created','ingesting','processing','completed','failed')),
    operator_id     text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_missions_aoi ON missions USING GIST (aoi);
CREATE INDEX idx_missions_status ON missions (status);

CREATE TABLE flight_sessions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id      uuid NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    platform        text NOT NULL,
    sensors         jsonb NOT NULL DEFAULT '[]',
    started_at      timestamptz NOT NULL,
    ended_at        timestamptz
);
CREATE INDEX idx_flight_sessions_mission ON flight_sessions (mission_id);

CREATE TABLE pipeline_runs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id          uuid NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    temporal_workflow_id text NOT NULL UNIQUE,
    preset              text NOT NULL DEFAULT 'standard',
    started_at          timestamptz,
    finished_at         timestamptz
);
CREATE INDEX idx_pipeline_runs_mission ON pipeline_runs (mission_id);

CREATE TABLE stage_executions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      uuid NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    stage       text NOT NULL,
    input_hash  text NOT NULL,
    output_uri  text,
    state       text NOT NULL DEFAULT 'pending'
                CHECK (state IN ('pending','running','succeeded','failed')),
    metrics     jsonb NOT NULL DEFAULT '{}',
    UNIQUE (run_id, stage, input_hash)   -- saga idempotency key, doc02 §5 / doc04 §5 rule 1
);

CREATE TABLE products (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id      uuid NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    kind            text NOT NULL,              -- O-1..O-9 product codes
    uri             text NOT NULL,
    crs             text NOT NULL,
    bbox            geometry NOT NULL,
    checksum        text NOT NULL,
    provenance_ref  text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_products_mission ON products (mission_id);
CREATE INDEX idx_products_bbox ON products USING GIST (bbox);

CREATE TABLE checkpoints (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id  uuid NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    label       text NOT NULL,
    geom        geometry(PointZ, 4326) NOT NULL,
    measured_by text NOT NULL,
    source      text NOT NULL           -- e.g. 'RTK survey', 'PPK basestation'
);

CREATE TABLE artifacts_lineage (
    parent_uri  text NOT NULL,
    child_uri   text NOT NULL,
    transform   text NOT NULL,
    PRIMARY KEY (parent_uri, child_uri)
);

COMMIT;
