package server

import (
	"context"
	"log/slog"
	"sync"

	"github.com/google/uuid"
	missionv1 "github.com/single-pass-recon/mission-svc/gen/mission/v1"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type MissionServer struct {
	missionv1.UnimplementedMissionServiceServer

	mu       sync.RWMutex
	missions map[string]*missionv1.CreateMissionResponse
	log      *slog.Logger
}

func NewMissionServer(log *slog.Logger) *MissionServer {
	return &MissionServer{
		missions: make(map[string]*missionv1.CreateMissionResponse),
		log:      log,
	}
}

func (s *MissionServer) CreateMission(ctx context.Context, req *missionv1.CreateMissionRequest) (*missionv1.CreateMissionResponse, error) {
	id := uuid.NewString()
	resp := &missionv1.CreateMissionResponse{
		MissionId: id,
		Status:    missionv1.MissionStatus_MISSION_STATUS_CREATED,
		CreatedAt: timestamppb.Now(),
	}

	s.mu.Lock()
	s.missions[id] = resp
	s.mu.Unlock()

	s.log.Info("mission created", "mission_id", id, "name", req.GetName())
	return resp, nil
}

func (s *MissionServer) GetStatus(ctx context.Context, req *missionv1.GetStatusRequest) (*missionv1.GetStatusResponse, error) {
	s.mu.RLock()
	m, ok := s.missions[req.GetMissionId()]
	s.mu.RUnlock()

	if !ok {
		return &missionv1.GetStatusResponse{
			MissionId: req.GetMissionId(),
			Status:    missionv1.MissionStatus_MISSION_STATUS_UNSPECIFIED,
		}, nil
	}

	return &missionv1.GetStatusResponse{
		MissionId: m.MissionId,
		Status:    m.Status,
	}, nil
}
