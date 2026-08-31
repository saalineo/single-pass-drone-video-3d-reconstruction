package server

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

type HTTPUploadResponse struct {
	MissionID          string `json:"mission_id"`
	RunID              string `json:"run_id"`
	TemporalWorkflowID string `json:"temporal_workflow_id"`
	Status             string `json:"status"`
	Message            string `json:"message"`
}

func (s *IngestServer) SetDBPool(pool *pgxpool.Pool) {
	s.dbPool = pool
}

func (s *IngestServer) HandleHTTPUpload(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")

	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}

	if r.Method != http.MethodPost {
		http.Error(w, `{"error":"Method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}

	// video upload guardrail (8Gb)
	r.Body = http.MaxBytesReader(w, r.Body, maxSegmentBytes)

	mr, err := r.MultipartReader()
	if err != nil {
		http.Error(w, fmt.Sprintf(`{"error": "expected multipart form: %v"}`, err), http.StatusBadRequest)
		return
	}

	var (
		missionName = ""
		preset      = "standard"
		tempFile    *os.File
		fileName    = ""
		fileSize    int64
		fileSHA256  string
	)

	for {
		part, err := mr.NextPart()
		if err == io.EOF {
			break
		}
		if err != nil {
			http.Error(w, fmt.Sprintf(`{"error": "read multipart stream: %v"}`, err), http.StatusBadRequest)
			return
		}

		formName := part.FormName()
		if formName == "name" {
			val, _ := io.ReadAll(part)
			missionName = strings.TrimSpace(string(val))
			part.Close()
			continue
		}
		if formName == "preset" {
			val, _ := io.ReadAll(part)
			preset = strings.TrimSpace(string(val))
			part.Close()
			continue
		}
		if formName == "video" || formName == "file" {
			fileName = part.FileName()
			tf, err := os.CreateTemp("", "ingest-upload-*.tmp")
			if err != nil {
				part.Close()
				http.Error(w, fmt.Sprintf(`{"error": "create temp file: %v"}`, err), http.StatusInternalServerError)
				return
			}
			tempFile = tf

			hasher := sha256.New()
			mw := io.MultiWriter(tempFile, hasher)
			n, err := io.Copy(mw, part)
			part.Close()
			if err != nil {
				tempFile.Close()
				os.Remove(tempFile.Name())
				http.Error(w, fmt.Sprintf(`{"error": "write video stream: %v"}`, err), http.StatusInternalServerError)
				return
			}
			fileSize = n
			fileSHA256 = hex.EncodeToString(hasher.Sum(nil))
		}
	}

	if tempFile == nil {
		http.Error(w, `{"error":"No video file found in field 'video' or 'file'"}`, http.StatusBadRequest)
		return
	}
	defer func() {
		tempFile.Close()
		os.Remove(tempFile.Name())
	}()

	missionID := uuid.New().String()
	if missionName == "" {
		if fileName != "" {
			missionName = strings.TrimSuffix(fileName, filepath.Ext(fileName))
		} else {
			missionName = fmt.Sprintf("Mission %s", missionID[:8])
		}
	}

	// Rewind temp file to stage into object store
	if _, err := tempFile.Seek(0, 0); err != nil {
		http.Error(w, fmt.Sprintf(`{"error": "seek temp file: %v"}`, err), http.StatusInternalServerError)
		return
	}

	ctx := r.Context()
	objectURI, err := s.store.StageAndCommit(ctx, missionID, 0, "web-ui-drag-drop", fileSHA256, tempFile, fileSize)
	if err != nil {
		http.Error(w, fmt.Sprintf(`{"error": "failed to store video: %v"}`, err), http.StatusInternalServerError)
		return
	}
	log.Printf("[ingest-svc] HTTP Upload committed object: %s (size: %d bytes)", objectURI, fileSize)

	// Record in PostgreSQL if DB pool is connected
	if s.dbPool != nil {
		const q = `
			INSERT INTO missions (id, name, classification, aoi, status, created_at, operator_id)
			VALUES ($1, $2, 'unclassified',
			        ST_SetSRID(ST_GeomFromGeoJSON('{"type":"Polygon","coordinates":[[[0,0],[0,0.001],[0.001,0.001],[0.001,0],[0,0]]]}'), 4326)::geography,
			        'ingesting', now(), 'web-operator')
			ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, status = 'ingesting'`
		if _, err := s.dbPool.Exec(ctx, q, missionID, missionName); err != nil {
			log.Printf("[ingest-svc] warning: failed to insert mission DB row: %v", err)
		}
	}

	// Launch Temporal Workflow
	runID, wfID, err := s.launcher.LaunchReconstruction(ctx, missionID, "http-session", preset, []uint32{0})
	if err != nil {
		log.Printf("[ingest-svc] warning: failed to launch Temporal workflow: %v", err)
		// Return response with error details so UI knows workflow couldn't start (e.g. namespace missing)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(HTTPUploadResponse{
			MissionID:          missionID,
			RunID:              runID,
			TemporalWorkflowID: wfID,
			Status:             "uploaded_workflow_pending",
			Message:            fmt.Sprintf("Video uploaded to object store, but workflow launch failed: %v", err),
		})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(HTTPUploadResponse{
		MissionID:          missionID,
		RunID:              runID,
		TemporalWorkflowID: wfID,
		Status:             "started",
		Message:            "Video uploaded successfully and 3D reconstruction workflow launched.",
	})
}
