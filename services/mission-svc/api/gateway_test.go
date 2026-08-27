package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net"
	"net/http"
	"testing"
	"time"

	missionv1 "github.com/single-pass-recon/mission-svc/gen/mission/v1"
	"github.com/single-pass-recon/mission-svc/db"
	"google.golang.org/grpc"
)

func TestGatewayRestEndpoints(t *testing.T) {
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen: %v", err)
	}

	grpcServer := grpc.NewServer()
	srv := NewServer(db.NewMissionStore(nil), db.NewRunStore(nil))
	missionv1.RegisterMissionServiceServer(grpcServer, srv)

	go func() {
		_ = grpcServer.Serve(lis)
	}()
	defer grpcServer.Stop()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	httpLis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen for http: %v", err)
	}
	httpAddr := httpLis.Addr().String()
	_ = httpLis.Close()

	go func() {
		_ = RunGateway(ctx, lis.Addr().String(), httpAddr, db.NewMissionStore(nil))
	}()

	time.Sleep(150 * time.Millisecond)

	// Test REST POST /v1/missions with invalid GeoJSON
	reqBody, _ := json.Marshal(map[string]interface{}{
		"name":                     "corridor-survey-014",
		"area_of_interest_geojson": "invalid-geojson",
		"classification":          "unclassified",
		"expected_sensors":         []string{"rgb"},
		"operator_id":              "op-42",
	})

	resp, err := http.Post("http://"+httpAddr+"/v1/missions", "application/json", bytes.NewReader(reqBody))
	if err != nil {
		t.Fatalf("POST /v1/missions failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusBadRequest && resp.StatusCode != http.StatusInternalServerError {
		t.Errorf("expected error status for invalid GeoJSON, got %d", resp.StatusCode)
	}
}
