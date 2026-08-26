package db

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

type MissionStore struct {
	pool *pgxpool.Pool
}

func NewMissionStore(pool *pgxpool.Pool) *MissionStore {
	return &MissionStore{pool: pool}
}

type CreateMissionParams struct {
	Name            string
	AOIGeoJSON      string
	Classification  string
	ExpectedSensors []string
	OperatorID      string
}

type StageStatus struct {
	Stage       string
	State       string
	ProgressPct float64
	OutputURI   string
}

func (s *MissionStore) CreateMission(ctx context.Context, p CreateMissionParams) (missionID string, err error) {
	if err := ValidatePolygonGeoJSON(p.AOIGeoJSON); err != nil {
		return "", fmt.Errorf("aoi validation: %w", err)
	}

	const q = `
		INSERT INTO missions (id, name, classification, aoi, status, created_at, operator_id)
		VALUES (gen_random_uuid(), $1, $2,
		        ST_SetSRID(ST_GeomFromGeoJSON($3), 4326)::geography,
		        'created', now(), $4)
		RETURNING id`

	row := s.pool.QueryRow(ctx, q, p.Name, p.Classification, p.AOIGeoJSON, p.OperatorID)
	if err := row.Scan(&missionID); err != nil {
		return "", fmt.Errorf("insert mission: %w", err)
	}
	return missionID, nil
}

func (s *MissionStore) GetMissionStatus(ctx context.Context, missionID string) (status string, stages []StageStatus, err error) {
	const q = `SELECT status FROM missions WHERE id = $1`
	row := s.pool.QueryRow(ctx, q, missionID)
	if err := row.Scan(&status); err != nil {
		return "", nil, fmt.Errorf("get mission status: %w", err)
	}

	const qStages = `
		SELECT se.stage, se.state, se.output_uri
		FROM stage_executions se
		JOIN pipeline_runs pr ON se.run_id = pr.id
		WHERE pr.mission_id = $1
		ORDER BY se.stage ASC`

	rows, err := s.pool.Query(ctx, qStages, missionID)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var st StageStatus
			var outputURI *string
			if err := rows.Scan(&st.Stage, &st.State, &outputURI); err == nil {
				if outputURI != nil {
					st.OutputURI = *outputURI
				}
				if st.State == "succeeded" || st.State == "completed" {
					st.ProgressPct = 100.0
				} else if st.State == "running" {
					st.ProgressPct = 50.0
				}
				stages = append(stages, st)
			}
		}
	}

	return status, stages, nil
}
