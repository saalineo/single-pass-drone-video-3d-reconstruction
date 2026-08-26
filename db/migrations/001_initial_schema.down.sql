BEGIN;
DROP TABLE IF EXISTS artifacts_lineage;
DROP TABLE IF EXISTS checkpoints;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS stage_executions;
DROP TABLE IF EXISTS pipeline_runs;
DROP TABLE IF EXISTS flight_sessions;
DROP TABLE IF EXISTS missions;
COMMIT;
