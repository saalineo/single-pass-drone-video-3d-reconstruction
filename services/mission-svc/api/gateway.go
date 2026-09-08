package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"time"

	"github.com/grpc-ecosystem/grpc-gateway/v2/runtime"
	"github.com/single-pass-recon/mission-svc/db"
	missionv1 "github.com/single-pass-recon/mission-svc/gen/mission/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type GatewayConfig struct {
	Presigner *StoragePresigner
}

func RunGateway(ctx context.Context, grpcAddr, httpAddr string, missions *db.MissionStore, presigner *StoragePresigner) error {
	grpcMux := runtime.NewServeMux()
	opts := []grpc.DialOption{grpc.WithTransportCredentials(insecure.NewCredentials())}
	if err := missionv1.RegisterMissionServiceHandlerFromEndpoint(ctx, grpcMux, grpcAddr, opts); err != nil {
		return fmt.Errorf("register gateway: %w", err)
	}

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}

		// Proxy /v1/ingest/upload to ingest-svc HTTP port 8081
		if strings.HasPrefix(r.URL.Path, "/v1/ingest/") {
			ingestURL, _ := url.Parse("http://127.0.0.1:8081")
			proxy := httputil.NewSingleHostReverseProxy(ingestURL)
			proxy.ServeHTTP(w, r)
			return
		}

		// REST POST /v1/storage/presign - Generate presigned URLs for remote workers
		if r.Method == http.MethodPost && r.URL.Path == "/v1/storage/presign" {
			w.Header().Set("Content-Type", "application/json")
			if presigner == nil {
				http.Error(w, `{"error": "presigner not configured"}`, http.StatusServiceUnavailable)
				return
			}
			var req struct {
				Bucket    string `json:"bucket"`
				ObjectKey string `json:"object_key"`
				Method    string `json:"method"` // "GET" or "PUT"
				ExpirySec int    `json:"expiry_seconds"`
			}
			if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
				http.Error(w, fmt.Sprintf(`{"error": "invalid request payload: %v"}`, err), http.StatusBadRequest)
				return
			}
			ttl := 4 * time.Hour // Default 4 hours for long reconstruction runs per Phase 3 / E-7
			if req.ExpirySec > 0 {
				ttl = time.Duration(req.ExpirySec) * time.Second
			}

			var signedURL string
			var err error
			if strings.ToUpper(req.Method) == "PUT" {
				signedURL, err = presigner.GeneratePresignedPut(r.Context(), req.Bucket, req.ObjectKey, ttl)
			} else {
				signedURL, err = presigner.GeneratePresignedGet(r.Context(), req.Bucket, req.ObjectKey, ttl)
			}
			if err != nil {
				http.Error(w, fmt.Sprintf(`{"error": %q}`, err.Error()), http.StatusInternalServerError)
				return
			}

			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"url":            signedURL,
				"bucket":         req.Bucket,
				"object_key":     req.ObjectKey,
				"method":         req.Method,
				"expiry_seconds": int(ttl.Seconds()),
			})
			return
		}

		// REST GET /v1/missions
		if r.Method == http.MethodGet && r.URL.Path == "/v1/missions" {
			w.Header().Set("Content-Type", "application/json")
			if missions == nil {
				_ = json.NewEncoder(w).Encode([]db.MissionRecord{})
				return
			}
			list, err := missions.ListMissions(r.Context())
			if err != nil {
				http.Error(w, fmt.Sprintf(`{"error": %q}`, err.Error()), http.StatusInternalServerError)
				return
			}
			_ = json.NewEncoder(w).Encode(list)
			return
		}

		// REST GET /v1/missions/{id}
		if r.Method == http.MethodGet && strings.HasPrefix(r.URL.Path, "/v1/missions/") {
			parts := strings.Split(strings.TrimPrefix(r.URL.Path, "/v1/missions/"), "/")
			if len(parts) == 1 && parts[0] != "" {
				missionID := parts[0]
				w.Header().Set("Content-Type", "application/json")
				if missions == nil {
					http.Error(w, `{"error": "mission not found"}`, http.StatusNotFound)
					return
				}
				m, err := missions.GetMission(r.Context(), missionID)
				if err != nil {
					http.Error(w, fmt.Sprintf(`{"error": %q}`, err.Error()), http.StatusNotFound)
					return
				}
				_ = json.NewEncoder(w).Encode(m)
				return
			}
			if len(parts) == 2 && parts[1] == "products" {
				missionID := parts[0]
				w.Header().Set("Content-Type", "application/json")
				if missions == nil {
					_ = json.NewEncoder(w).Encode([]db.ProductRecord{})
					return
				}
				prods, err := missions.GetMissionProducts(r.Context(), missionID)
				if err != nil {
					http.Error(w, fmt.Sprintf(`{"error": %q}`, err.Error()), http.StatusInternalServerError)
					return
				}
				_ = json.NewEncoder(w).Encode(prods)
				return
			}
		}

		grpcMux.ServeHTTP(w, r)
	})

	return http.ListenAndServe(httpAddr, handler)
}
