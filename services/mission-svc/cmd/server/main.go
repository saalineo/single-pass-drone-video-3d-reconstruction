package main

import (
	"context"
	"log"
	"net"
	"os"
	"strconv"
	"time"

	"github.com/single-pass-recon/mission-svc/api"
	"github.com/single-pass-recon/mission-svc/db"
	missionv1 "github.com/single-pass-recon/mission-svc/gen/mission/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	healthv1 "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"
)

func getEnvOrDefault(key, fallback string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return fallback
}

func main() {
	grpcPort := getEnvOrDefault("MISSION_GRPC_PORT", "50051")
	httpPort := getEnvOrDefault("MISSION_HTTP_PORT", "8080")
	dsn := getEnvOrDefault("POSTGRES_DSN", "postgres://postgres:postgres@localhost:5432/reconstruction?sslmode=disable")
	maxConnsStr := getEnvOrDefault("POSTGRES_MAX_CONNS", "10")

	minioEndpoint := getEnvOrDefault("MINIO_ENDPOINT", "localhost:9000")
	minioAccessKey := getEnvOrDefault("MINIO_ACCESS_KEY", "minioadmin")
	minioSecretKey := getEnvOrDefault("MINIO_SECRET_KEY", "minioadmin")
	minioSecure := os.Getenv("MINIO_SECURE") == "true" || os.Getenv("MINIO_USE_TLS") == "true"

	maxConns, _ := strconv.Atoi(maxConnsStr)

	ctx := context.Background()

	pool, err := db.NewPool(ctx, dsn, int32(maxConns))
	if err != nil {
		log.Printf("warning: db connection failed (%v), continuing in degraded mode", err)
	}

	missionStore := db.NewMissionStore(pool)
	runStore := db.NewRunStore(pool)

	presigner, err := api.NewStoragePresigner(minioEndpoint, minioAccessKey, minioSecretKey, minioSecure)
	if err != nil {
		log.Printf("warning: failed to initialize storage presigner (%v)", err)
	}

	grpcServer := grpc.NewServer()
	srv := api.NewServer(missionStore, runStore)
	missionv1.RegisterMissionServiceServer(grpcServer, srv)

	healthSrv := health.NewServer()
	healthv1.RegisterHealthServer(grpcServer, healthSrv)
	healthSrv.SetServingStatus("mission.v1.MissionService", healthv1.HealthCheckResponse_SERVING)

	reflection.Register(grpcServer)

	grpcAddr := ":" + grpcPort
	lis, err := net.Listen("tcp", grpcAddr)
	if err != nil {
		log.Fatalf("failed to listen on gRPC port %s: %v", grpcPort, err)
	}

	go func() {
		log.Printf("mission-svc gRPC listening on %s", grpcAddr)
		if err := grpcServer.Serve(lis); err != nil {
			log.Fatalf("grpc server exited: %v", err)
		}
	}()

	// Give gRPC server a moment to start before gateway dials localhost
	time.Sleep(100 * time.Millisecond)

	httpAddr := ":" + httpPort
	log.Printf("mission-svc REST gateway listening on %s", httpAddr)
	if err := api.RunGateway(ctx, "127.0.0.1:"+grpcPort, httpAddr, missionStore, presigner); err != nil {
		log.Fatalf("gateway server exited: %v", err)
	}
}
