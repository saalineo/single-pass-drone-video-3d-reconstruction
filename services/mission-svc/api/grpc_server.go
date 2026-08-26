package api

import (
	"context"

	missionv1 "github.com/single-pass-recon/mission-svc/gen/mission/v1"
	"github.com/single-pass-recon/mission-svc/db"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type Server struct {
	missionv1.UnimplementedMissionServiceServer
	missions *db.MissionStore
	runs     *db.RunStore
}

func NewServer(missions *db.MissionStore, runs *db.RunStore) *Server {
	return &Server{
		missions: missions,
		runs:     runs,
	}
}

func (s *Server) CreateMission(ctx context.Context, req *missionv1.CreateMissionRequest) (*missionv1.CreateMissionResponse, error) {
	if req.GetName() == "" || req.GetAreaOfInterestGeojson() == "" {
		return nil, status.Error(codes.InvalidArgument, "name and area_of_interest_geojson are required")
	}

	id, err := s.missions.CreateMission(ctx, db.CreateMissionParams{
		Name:            req.GetName(),
		AOIGeoJSON:      req.GetAreaOfInterestGeojson(),
		Classification:  req.GetClassification(),
		ExpectedSensors: req.GetExpectedSensors(),
		OperatorID:      req.GetOperatorId(),
	})
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "%v", err)
	}
	return &missionv1.CreateMissionResponse{MissionId: id}, nil
}

func (s *Server) GetMissionStatus(ctx context.Context, req *missionv1.GetMissionStatusRequest) (*missionv1.GetMissionStatusResponse, error) {
	if req.GetMissionId() == "" {
		return nil, status.Error(codes.InvalidArgument, "mission_id is required")
	}

	mStatus, dbStages, err := s.missions.GetMissionStatus(ctx, req.GetMissionId())
	if err != nil {
		return nil, status.Errorf(codes.NotFound, "mission not found: %v", err)
	}

	var stages []*missionv1.StageStatus
	for _, st := range dbStages {
		stages = append(stages, &missionv1.StageStatus{
			Stage:       st.Stage,
			State:       st.State,
			ProgressPct: st.ProgressPct,
			OutputUri:   st.OutputURI,
		})
	}

	return &missionv1.GetMissionStatusResponse{
		MissionId: req.GetMissionId(),
		Status:    mStatus,
		Stages:    stages,
	}, nil
}

func (s *Server) CreateRun(ctx context.Context, req *missionv1.CreateRunRequest) (*missionv1.CreateRunResponse, error) {
	if req.GetMissionId() == "" {
		return nil, status.Error(codes.InvalidArgument, "mission_id is required")
	}

	runID, wfID, err := s.runs.CreateRun(ctx, req.GetMissionId(), req.GetPreset())
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to create run: %v", err)
	}

	return &missionv1.CreateRunResponse{
		RunId:              runID,
		TemporalWorkflowId: wfID,
	}, nil
}
