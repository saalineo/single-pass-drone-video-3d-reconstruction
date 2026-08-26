package main

import (
	"log/slog"
	"net"
	"os"

	missionv1 "github.com/single-pass-recon/mission-svc/gen/mission/v1"
	"github.com/single-pass-recon/mission-svc/internal/server"
	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	healthv1 "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"
)

const defaultAddr = ":50051"

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	addr := os.Getenv("GRPC_LISTEN_ADDR")
	if addr == "" {
		addr = defaultAddr
	}

	lis, err := net.Listen("tcp", addr)
	if err != nil {
		log.Error("failed to listen", "err", err)
		os.Exit(1)
	}

	grpcServer := grpc.NewServer()
	missionv1.RegisterMissionServiceServer(grpcServer, server.NewMissionServer(log))

	healthSrv := health.NewServer()
	healthv1.RegisterHealthServer(grpcServer, healthSrv)
	healthSrv.SetServingStatus("recon.mission.v1.MissionService", healthv1.HealthCheckResponse_SERVING)

	reflection.Register(grpcServer)

	log.Info("mission-svc listening", "addr", addr)
	if err := grpcServer.Serve(lis); err != nil {
		log.Error("grpc server stopped", "err", err)
		os.Exit(1)
	}
}
