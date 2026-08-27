package db

import (
	"context"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

type RunStore struct {
	pool *pgxpool.Pool
}

func NewRunStore(pool *pgxpool.Pool) *RunStore {
	return &RunStore{pool: pool}
}

func (s *RunStore) CreateRun(ctx context.Context, missionID, preset string) (runID, workflowID string, err error) {
	id := uuid.New()
	wfID := fmt.Sprintf("recon-%s", id.String())

	if preset == "" {
		preset = "standard"
	}
	if s.pool == nil {
		return id.String(), wfID, nil
	}

	const q = `
		INSERT INTO pipeline_runs (id, mission_id, temporal_workflow_id, preset, started_at)
		VALUES ($1, $2, $3, $4, now())
		ON CONFLICT (temporal_workflow_id) DO UPDATE SET preset = EXCLUDED.preset
		RETURNING id, temporal_workflow_id`

	row := s.pool.QueryRow(ctx, q, id, missionID, wfID, preset)
	if err := row.Scan(&runID, &workflowID); err != nil {
		const qLookup = `SELECT id, temporal_workflow_id FROM pipeline_runs WHERE mission_id = $1 ORDER BY started_at DESC LIMIT 1`
		if lErr := s.pool.QueryRow(ctx, qLookup, missionID).Scan(&runID, &workflowID); lErr == nil {
			return runID, workflowID, nil
		}
		return "", "", fmt.Errorf("insert pipeline_run: %w", err)
	}
	return runID, workflowID, nil
}
