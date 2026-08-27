package main

import (
	"log"
	"net"
	"os"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
	ingestv1 "github.com/single-pass-recon/ingest-svc/gen/ingest/v1"
	"github.com/single-pass-recon/ingest-svc/server"
	"go.temporal.io/sdk/client"
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
	endpoint := getEnvOrDefault("MINIO_ENDPOINT", "localhost:9000")
	accessKey := os.Getenv("MINIO_ACCESS_KEY")
	secretKey := os.Getenv("MINIO_SECRET_KEY")
	useTLS := os.Getenv("MINIO_USE_TLS") == "true"
	bucket := getEnvOrDefault("INGEST_RAW_BUCKET", "recon-raw")
	port := getEnvOrDefault("INGEST_GRPC_PORT", "50051")

	mc, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(accessKey, secretKey, ""),
		Secure: useTLS,
	})
	if err != nil {
		log.Fatalf("minio client: %v", err)
	}

	store := server.NewVideoStore(&server.MinioWrapper{Client: mc}, bucket)
	grpcServer := grpc.NewServer(grpc.MaxRecvMsgSize(8 << 20)) // 8 MiB max recv message

	temporalHostPort := getEnvOrDefault("TEMPORAL_HOST_PORT", "localhost:7233")
	temporalNamespace := getEnvOrDefault("TEMPORAL_NAMESPACE", "recon")
	temporalClient, err := client.Dial(client.Options{HostPort: temporalHostPort, Namespace: temporalNamespace})
	if err != nil {
		log.Fatalf("temporal client: %v", err)
	}
	defer temporalClient.Close()

	launcher := &server.TemporalWorkflowLauncher{Client: temporalClient, Store: store}
	srv := server.NewIngestServer(store, launcher)
	ingestv1.RegisterIngestServiceServer(grpcServer, srv)

	healthSrv := health.NewServer()
	healthv1.RegisterHealthServer(grpcServer, healthSrv)
	healthSrv.SetServingStatus("ingest.v1.IngestService", healthv1.HealthCheckResponse_SERVING)

	reflection.Register(grpcServer)

	lis, err := net.Listen("tcp", ":"+port)
	if err != nil {
		log.Fatalf("failed to listen on port %s: %v", port, err)
	}

	log.Printf("ingest-svc listening on :%s", port)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("grpc server exited: %v", err)
	}
}
