package api

import (
	"context"
	"fmt"
	"net/http"

	"github.com/grpc-ecosystem/grpc-gateway/v2/runtime"
	missionv1 "github.com/single-pass-recon/mission-svc/gen/mission/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func RunGateway(ctx context.Context, grpcAddr, httpAddr string) error {
	mux := runtime.NewServeMux()
	opts := []grpc.DialOption{grpc.WithTransportCredentials(insecure.NewCredentials())}
	if err := missionv1.RegisterMissionServiceHandlerFromEndpoint(ctx, mux, grpcAddr, opts); err != nil {
		return fmt.Errorf("register gateway: %w", err)
	}
	return http.ListenAndServe(httpAddr, mux)
}
