package main

import (
	"log/slog"
	"net"
	"os"

	ingestv1 "github.com/single-pass-recon/ingest-svc/gen/ingest/v1"
	"github.com/single-pass-recon/ingest-svc/internal/server"
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
	ingestv1.RegisterIngestServiceServer(grpcServer, server.NewIngestServer(log))

	healthSrv := health.NewServer()
	healthv1.RegisterHealthServer(grpcServer, healthSrv)
	healthSrv.SetServingStatus("recon.ingest.v1.IngestService", healthv1.HealthCheckResponse_SERVING)

	reflection.Register(grpcServer)

	log.Info("ingest-svc listening", "addr", addr)
	if err := grpcServer.Serve(lis); err != nil {
		log.Error("grpc server stopped", "err", err)
		os.Exit(1)
	}
}
