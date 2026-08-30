package main

import (
	"context"
	"log"
	"net"
	"net/http"
	"os"

	"github.com/jackc/pgx/v5/pgxpool"
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
	grpcPort := getEnvOrDefault("INGEST_GRPC_PORT", "50052")
	httpPort := getEnvOrDefault("INGEST_HTTP_PORT", "8081")
	dsn := getEnvOrDefault("POSTGRES_DSN", "postgres://postgres:postgres@localhost:5432/reconstruction?sslmode=disable")

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
		log.Printf("warning: temporal client connection failed (%v), continuing without temporal workflow auto-start", err)
	} else {
		defer temporalClient.Close()
	}

	var launcher server.WorkflowLauncher
	if temporalClient != nil {
		launcher = &server.TemporalWorkflowLauncher{Client: temporalClient, Store: store}
	} else {
		launcher = &server.LazyTemporalWorkflowLauncher{
			HostPort:  temporalHostPort,
			Namespace: temporalNamespace,
			Store:     store,
		}
	}

	srv := server.NewIngestServer(store, launcher)

	// Connect PostgreSQL if available
	ctx := context.Background()
	if pool, err := pgxpool.New(ctx, dsn); err == nil {
		srv.SetDBPool(pool)
		defer pool.Close()
	} else {
		log.Printf("warning: db connection failed (%v), continuing in degraded mode", err)
	}

	ingestv1.RegisterIngestServiceServer(grpcServer, srv)

	healthSrv := health.NewServer()
	healthv1.RegisterHealthServer(grpcServer, healthSrv)
	healthSrv.SetServingStatus("ingest.v1.IngestService", healthv1.HealthCheckResponse_SERVING)

	reflection.Register(grpcServer)

	// Start HTTP Server for UI Drag-and-Drop Video Uploads
	httpMux := http.NewServeMux()
	httpMux.HandleFunc("/v1/ingest/upload", srv.HandleHTTPUpload)

	httpServer := &http.Server{
		Addr:    ":" + httpPort,
		Handler: httpMux,
	}

	go func() {
		log.Printf("ingest-svc HTTP listening on :%s", httpPort)
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("ingest-svc http server exited: %v", err)
		}
	}()

	lis, err := net.Listen("tcp", ":"+grpcPort)
	if err != nil {
		log.Fatalf("failed to listen on port %s: %v", grpcPort, err)
	}

	log.Printf("ingest-svc gRPC listening on :%s", grpcPort)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("grpc server exited: %v", err)
	}
}
