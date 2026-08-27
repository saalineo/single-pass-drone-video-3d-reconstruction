package db

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

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
	if s.pool == nil {
		return "", fmt.Errorf("database unavailable")
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
	if s.pool == nil {
		return "created", nil, nil
	}
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

type MissionRecord struct {
	ID              string      `json:"id"`
	Name            string      `json:"name"`
	Status          string      `json:"status"`
	CreatedAt       string      `json:"createdAt"`
	AreaOfInterest  any         `json:"areaOfInterest"`
	Classification  string      `json:"classification"`
	ExpectedSensors []string    `json:"expectedSensors"`
	AreaSqKm        float64     `json:"areaSqKm"`
	Stages          []any       `json:"stages"`
}

type ProductRecord struct {
	ID            string    `json:"id"`
	MissionID     string    `json:"missionId"`
	Kind          string    `json:"kind"`
	Format        string    `json:"format"`
	URL           string    `json:"url"`
	CRS           string    `json:"crs"`
	BBox          []float64 `json:"bbox"`
	Checksum      string    `json:"checksum"`
	Quality       string    `json:"quality"`
	ProvenanceRef *string   `json:"provenanceRef"`
	SizeBytes     int64     `json:"sizeBytes"`
	CoveragePct   *float64  `json:"coveragePct,omitempty"`
}

func (s *MissionStore) ListMissions(ctx context.Context) ([]MissionRecord, error) {
	if s.pool == nil {
		return []MissionRecord{}, nil
	}
	const q = `
		SELECT id, name, classification, status, operator_id, created_at,
		       ST_AsGeoJSON(aoi::geometry) as aoi_geojson,
		       ST_Area(aoi) / 1000000.0 as area_sqkm
		FROM missions
		ORDER BY created_at DESC`
	rows, err := s.pool.Query(ctx, q)
	if err != nil {
		return nil, fmt.Errorf("list missions: %w", err)
	}
	defer rows.Close()

	var results []MissionRecord
	for rows.Next() {
		var m MissionRecord
		var aoiGeoJSON, operatorID string
		var t time.Time
		if err := rows.Scan(&m.ID, &m.Name, &m.Classification, &m.Status, &operatorID, &t, &aoiGeoJSON, &m.AreaSqKm); err != nil {
			return nil, fmt.Errorf("scan mission: %w", err)
		}
		m.CreatedAt = t.UTC().Format(time.RFC3339)
		m.ExpectedSensors = []string{"rgb"}
		m.Stages = []any{}
		_ = json.Unmarshal([]byte(aoiGeoJSON), &m.AreaOfInterest)
		results = append(results, m)
	}
	if results == nil {
		results = []MissionRecord{}
	}
	return results, nil
}

func (s *MissionStore) GetMission(ctx context.Context, id string) (*MissionRecord, error) {
	if s.pool == nil {
		return nil, fmt.Errorf("mission not found: degraded mode (no database)")
	}
	const q = `
		SELECT id, name, classification, status, operator_id, created_at,
		       ST_AsGeoJSON(aoi::geometry) as aoi_geojson,
		       ST_Area(aoi) / 1000000.0 as area_sqkm
		FROM missions
		WHERE id = $1`
	var m MissionRecord
	var aoiGeoJSON, operatorID string
	var t time.Time
	if err := s.pool.QueryRow(ctx, q, id).Scan(&m.ID, &m.Name, &m.Classification, &m.Status, &operatorID, &t, &aoiGeoJSON, &m.AreaSqKm); err != nil {
		return nil, fmt.Errorf("get mission: %w", err)
	}
	m.CreatedAt = t.UTC().Format(time.RFC3339)
	m.ExpectedSensors = []string{"rgb"}
	m.Stages = []any{}
	_ = json.Unmarshal([]byte(aoiGeoJSON), &m.AreaOfInterest)
	return &m, nil
}

func (s *MissionStore) GetMissionProducts(ctx context.Context, missionID string) ([]ProductRecord, error) {
	if s.pool == nil {
		return []ProductRecord{}, nil
	}
	const q = `
		SELECT id, mission_id, kind, uri, crs, checksum, provenance_ref, created_at
		FROM products
		WHERE mission_id = $1
		ORDER BY created_at ASC`
	rows, err := s.pool.Query(ctx, q, missionID)
	if err != nil {
		return nil, fmt.Errorf("get products: %w", err)
	}
	defer rows.Close()

	var results []ProductRecord
	for rows.Next() {
		var p ProductRecord
		var t time.Time
		if err := rows.Scan(&p.ID, &p.MissionID, &p.Kind, &p.URL, &p.CRS, &p.Checksum, &p.ProvenanceRef, &t); err != nil {
			return nil, fmt.Errorf("scan product: %w", err)
		}
		p.Quality = "survey"
		p.Format = p.Kind
		p.BBox = []float64{0, 0, 0, 0}
		results = append(results, p)
	}
	if results == nil {
		results = []ProductRecord{}
	}
	return results, nil
}
