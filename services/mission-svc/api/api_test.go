package api

import (
	"context"
	"testing"

	missionv1 "github.com/single-pass-recon/mission-svc/gen/mission/v1"
	"github.com/single-pass-recon/mission-svc/db"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestCreateMissionValidation(t *testing.T) {
	srv := NewServer(db.NewMissionStore(nil), db.NewRunStore(nil))
	ctx := context.Background()

	// Empty name
	_, err := srv.CreateMission(ctx, &missionv1.CreateMissionRequest{
		Name:                      "",
		AreaOfInterestGeojson:     `{"type":"Polygon","coordinates":[[[0,0],[0,1],[1,1],[1,0],[0,0]]]}`,
	})
	if err == nil {
		t.Fatalf("expected error for empty name, got nil")
	}
	st, _ := status.FromError(err)
	if st.Code() != codes.InvalidArgument {
		t.Errorf("expected InvalidArgument, got %v", st.Code())
	}

	// Invalid GeoJSON
	_, err = srv.CreateMission(ctx, &missionv1.CreateMissionRequest{
		Name:                      "test-mission",
		AreaOfInterestGeojson:     `invalid-geojson`,
	})
	if err == nil {
		t.Fatalf("expected error for invalid geojson, got nil")
	}
	st, _ = status.FromError(err)
	if st.Code() != codes.InvalidArgument {
		t.Errorf("expected InvalidArgument, got %v", st.Code())
	}
}

func TestCreateRunValidation(t *testing.T) {
	srv := NewServer(db.NewMissionStore(nil), db.NewRunStore(nil))
	ctx := context.Background()

	_, err := srv.CreateRun(ctx, &missionv1.CreateRunRequest{
		MissionId: "",
	})
	if err == nil {
		t.Fatalf("expected error for empty mission_id, got nil")
	}
	st, _ := status.FromError(err)
	if st.Code() != codes.InvalidArgument {
		t.Errorf("expected InvalidArgument, got %v", st.Code())
	}
}
