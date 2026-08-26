package server

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
	ingestv1 "github.com/single-pass-recon/ingest-svc/gen/ingest/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
)

func decodeAWSChunked(b []byte) []byte {
	var result []byte
	buf := strings.NewReader(string(b))
	for {
		line, err := readLine(buf)
		if err != nil || line == "" {
			break
		}
		parts := strings.SplitN(line, ";", 2)
		var size int
		fmt.Sscanf(parts[0], "%x", &size)
		if size == 0 {
			break
		}
		chunk := make([]byte, size)
		n, _ := io.ReadFull(buf, chunk)
		result = append(result, chunk[:n]...)
		_, _ = readLine(buf) // consume trailing \r\n
	}
	return result
}

func readLine(r *strings.Reader) (string, error) {
	var line []byte
	for {
		b, err := r.ReadByte()
		if err != nil {
			return strings.TrimSpace(string(line)), err
		}
		if b == '\n' {
			return strings.TrimSpace(string(line)), nil
		}
		line = append(line, b)
	}
}

type mockObject struct {
	data        []byte
	contentType string
}

type mockS3Server struct {
	mu      sync.Mutex
	objects map[string]mockObject
	t       *testing.T
}

func newMockS3Server(t *testing.T) (*httptest.Server, *mockS3Server) {
	m := &mockS3Server{objects: make(map[string]mockObject), t: t}
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		m.mu.Lock()
		defer m.mu.Unlock()

		key := r.URL.Path

		// Bucket level operations
		if key == "/recon-raw" || key == "/recon-raw/" {
			if r.URL.Query().Has("location") {
				w.Header().Set("Content-Type", "application/xml")
				w.WriteHeader(http.StatusOK)
				w.Write([]byte(`<?xml version="1.0" encoding="UTF-8"?><LocationResponse xmlns="http://s3.amazonaws.com/doc/2006-03-01/"/>`))
				return
			}
			w.WriteHeader(http.StatusOK)
			return
		}

		switch r.Method {
		case http.MethodPut:
			copySource := r.Header.Get("X-Amz-Copy-Source")
			if copySource != "" {
				srcKey := copySource
				if !strings.HasPrefix(srcKey, "/") {
					srcKey = "/" + srcKey
				}
				srcObj, ok := m.objects[srcKey]
				if !ok {
					w.Header().Set("Content-Type", "application/xml")
					w.WriteHeader(http.StatusNotFound)
					w.Write([]byte(fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?><Error><Code>NoSuchKey</Code><Message>The specified key does not exist.</Message><Key>%s</Key></Error>`, srcKey)))
					return
				}
				m.objects[key] = mockObject{
					data:        append([]byte(nil), srcObj.data...),
					contentType: srcObj.contentType,
				}
				w.Header().Set("Content-Type", "application/xml")
				w.WriteHeader(http.StatusOK)
				w.Write([]byte(`<?xml version="1.0" encoding="UTF-8"?><CopyObjectResult><LastModified>2026-08-26T00:00:00Z</LastModified><ETag>"12345678901234567890123456789012"</ETag></CopyObjectResult>`))
				return
			}
			data, _ := io.ReadAll(r.Body)
			if r.Header.Get("Content-Encoding") == "aws-chunked" || r.Header.Get("X-Amz-Content-Sha256") == "STREAMING-AWS4-HMAC-SHA256-PAYLOAD" {
				data = decodeAWSChunked(data)
			}
			m.objects[key] = mockObject{
				data:        data,
				contentType: r.Header.Get("Content-Type"),
			}
			w.Header().Set("ETag", `"12345678901234567890123456789012"`)
			w.WriteHeader(http.StatusOK)

		case http.MethodGet:
			obj, ok := m.objects[key]
			if !ok {
				w.Header().Set("Content-Type", "application/xml")
				w.WriteHeader(http.StatusNotFound)
				w.Write([]byte(fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?><Error><Code>NoSuchKey</Code><Message>The specified key does not exist.</Message><Key>%s</Key></Error>`, key)))
				return
			}
			w.Header().Set("Content-Length", fmt.Sprintf("%d", len(obj.data)))
			w.Header().Set("Last-Modified", time.Now().UTC().Format(http.TimeFormat))
			w.Header().Set("ETag", `"12345678901234567890123456789012"`)
			if obj.contentType != "" {
				w.Header().Set("Content-Type", obj.contentType)
			}
			if r.Header.Get("Range") != "" && len(obj.data) > 0 {
				w.Header().Set("Content-Range", fmt.Sprintf("bytes 0-%d/%d", len(obj.data)-1, len(obj.data)))
				w.WriteHeader(http.StatusPartialContent)
			} else {
				w.WriteHeader(http.StatusOK)
			}
			w.Write(obj.data)

		case http.MethodHead:
			obj, ok := m.objects[key]
			if !ok {
				w.Header().Set("Content-Type", "application/xml")
				w.WriteHeader(http.StatusNotFound)
				return
			}
			w.Header().Set("Content-Length", fmt.Sprintf("%d", len(obj.data)))
			w.Header().Set("Last-Modified", time.Now().UTC().Format(http.TimeFormat))
			w.Header().Set("ETag", `"12345678901234567890123456789012"`)
			if obj.contentType != "" {
				w.Header().Set("Content-Type", obj.contentType)
			}
			w.WriteHeader(http.StatusOK)

		case http.MethodDelete:
			delete(m.objects, key)
			w.WriteHeader(http.StatusNoContent)

		default:
			m.t.Logf("MOCK S3 UNHANDLED: %s %s", r.Method, r.URL.String())
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		}
	}))
	return ts, m
}

func setupTestServer(t *testing.T) (ingestv1.IngestServiceClient, func()) {
	t.Helper()
	s3HTTP, _ := newMockS3Server(t)

	host := strings.TrimPrefix(s3HTTP.URL, "http://")
	mc, err := minio.New(host, &minio.Options{
		Creds:  credentials.NewStaticV4("testaccess", "testsecret", ""),
		Secure: false,
	})
	if err != nil {
		t.Fatalf("failed to create minio client: %v", err)
	}

	videoStore := NewVideoStore(&MinioWrapper{Client: mc}, "recon-raw")
	ingestServer := NewIngestServer(videoStore, nil)

	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen: %v", err)
	}

	grpcServer := grpc.NewServer()
	ingestv1.RegisterIngestServiceServer(grpcServer, ingestServer)

	go func() {
		_ = grpcServer.Serve(lis)
	}()

	conn, err := grpc.Dial(lis.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatalf("failed to dial: %v", err)
	}

	client := ingestv1.NewIngestServiceClient(conn)

	cleanup := func() {
		_ = conn.Close()
		grpcServer.Stop()
		_ = lis.Close()
		s3HTTP.Close()
	}

	return client, cleanup
}

func TestUploadVideoStream_SuccessAndDeduplication(t *testing.T) {
	client, cleanup := setupTestServer(t)
	defer cleanup()

	ctx := context.Background()
	payloadData := []byte("test video stream content chunk 1 chunk 2")
	hash := sha256.Sum256(payloadData)
	sha256Hex := hex.EncodeToString(hash[:])

	// 1. Initial Upload
	stream, err := client.UploadVideoStream(ctx)
	if err != nil {
		t.Fatalf("UploadVideoStream call failed: %v", err)
	}

	err = stream.Send(&ingestv1.UploadVideoChunk{
		Payload: &ingestv1.UploadVideoChunk_Header{
			Header: &ingestv1.UploadVideoHeader{
				MissionId:       "mission-101",
				FlightSessionId: "session-001",
				SegmentIndex:    0,
				Sha256Hex:       sha256Hex,
				TotalBytes:      uint64(len(payloadData)),
				Producer:        "edge-kit/1.3.2",
			},
		},
	})
	if err != nil {
		t.Fatalf("failed to send header: %v", err)
	}

	// Send chunk
	err = stream.Send(&ingestv1.UploadVideoChunk{
		Payload: &ingestv1.UploadVideoChunk_ChunkData{
			ChunkData: payloadData,
		},
	})
	if err != nil {
		t.Fatalf("failed to send chunk: %v", err)
	}

	resp, err := stream.CloseAndRecv()
	if err != nil {
		t.Fatalf("CloseAndRecv failed: %v", err)
	}

	if resp.GetDeduplicated() {
		t.Errorf("expected deduplicated=false on first upload")
	}
	if resp.GetBytesReceived() != uint64(len(payloadData)) {
		t.Errorf("got bytes_received=%d, want %d", resp.GetBytesReceived(), len(payloadData))
	}
	if resp.GetSha256Hex() != sha256Hex {
		t.Errorf("got sha256_hex=%s, want %s", resp.GetSha256Hex(), sha256Hex)
	}

	// 2. Re-upload identical segment -> expect deduplicated = true
	stream2, err := client.UploadVideoStream(ctx)
	if err != nil {
		t.Fatalf("second UploadVideoStream call failed: %v", err)
	}

	err = stream2.Send(&ingestv1.UploadVideoChunk{
		Payload: &ingestv1.UploadVideoChunk_Header{
			Header: &ingestv1.UploadVideoHeader{
				MissionId:       "mission-101",
				FlightSessionId: "session-001",
				SegmentIndex:    0,
				Sha256Hex:       sha256Hex,
				TotalBytes:      uint64(len(payloadData)),
				Producer:        "edge-kit/1.3.2",
			},
		},
	})
	if err != nil {
		t.Fatalf("failed to send header on stream2: %v", err)
	}

	resp2, err := stream2.CloseAndRecv()
	if err != nil {
		t.Fatalf("stream2 CloseAndRecv failed: %v", err)
	}

	if !resp2.GetDeduplicated() {
		t.Errorf("expected deduplicated=true on second upload")
	}
}

func TestUploadVideoStream_HashMismatch(t *testing.T) {
	client, cleanup := setupTestServer(t)
	defer cleanup()

	ctx := context.Background()
	payloadData := []byte("corrupted stream data")
	wrongSHA256 := strings.Repeat("a", 64)

	stream, err := client.UploadVideoStream(ctx)
	if err != nil {
		t.Fatalf("UploadVideoStream call failed: %v", err)
	}

	_ = stream.Send(&ingestv1.UploadVideoChunk{
		Payload: &ingestv1.UploadVideoChunk_Header{
			Header: &ingestv1.UploadVideoHeader{
				MissionId:       "mission-102",
				FlightSessionId: "session-001",
				SegmentIndex:    1,
				Sha256Hex:       wrongSHA256,
				TotalBytes:      uint64(len(payloadData)),
				Producer:        "edge-kit/1.3.2",
			},
		},
	})

	_ = stream.Send(&ingestv1.UploadVideoChunk{
		Payload: &ingestv1.UploadVideoChunk_ChunkData{
			ChunkData: payloadData,
		},
	})

	_, err = stream.CloseAndRecv()
	if err == nil {
		t.Fatalf("expected error on hash mismatch, got nil")
	}

	st, _ := status.FromError(err)
	if st.Code() != codes.DataLoss {
		t.Errorf("expected code DataLoss, got %v", st.Code())
	}
}

func TestUploadVideoStream_Truncated(t *testing.T) {
	client, cleanup := setupTestServer(t)
	defer cleanup()

	ctx := context.Background()
	payloadData := []byte("short")
	hash := sha256.Sum256(payloadData)

	stream, err := client.UploadVideoStream(ctx)
	if err != nil {
		t.Fatalf("UploadVideoStream call failed: %v", err)
	}

	_ = stream.Send(&ingestv1.UploadVideoChunk{
		Payload: &ingestv1.UploadVideoChunk_Header{
			Header: &ingestv1.UploadVideoHeader{
				MissionId:       "mission-103",
				FlightSessionId: "session-001",
				SegmentIndex:    2,
				Sha256Hex:       hex.EncodeToString(hash[:]),
				TotalBytes:      100, // declared 100, sending 5 bytes
				Producer:        "edge-kit/1.3.2",
			},
		},
	})

	_ = stream.Send(&ingestv1.UploadVideoChunk{
		Payload: &ingestv1.UploadVideoChunk_ChunkData{
			ChunkData: payloadData,
		},
	})

	_, err = stream.CloseAndRecv()
	if err == nil {
		t.Fatalf("expected error on truncated stream, got nil")
	}

	st, _ := status.FromError(err)
	if st.Code() != codes.DataLoss {
		t.Errorf("expected code DataLoss, got %v", st.Code())
	}
}

func TestGetUploadOffsetAndFinalizeIngest(t *testing.T) {
	client, cleanup := setupTestServer(t)
	defer cleanup()

	ctx := context.Background()

	// 1. FinalizeIngest before upload -> expect FailedPrecondition
	_, err := client.FinalizeIngest(ctx, &ingestv1.FinalizeIngestRequest{
		MissionId:       "mission-201",
		FlightSessionId: "session-201",
		SegmentIndices:  []uint32{0},
		Preset:          "standard",
	})
	if err == nil {
		t.Fatalf("expected error finalizing uncommitted segment, got nil")
	}
	st, _ := status.FromError(err)
	if st.Code() != codes.FailedPrecondition {
		t.Errorf("expected FailedPrecondition, got %v", st.Code())
	}

	// 2. Upload segment 0
	payloadData := []byte("valid segment payload for finalize test")
	hash := sha256.Sum256(payloadData)
	sha256Hex := hex.EncodeToString(hash[:])

	stream, err := client.UploadVideoStream(ctx)
	if err != nil {
		t.Fatalf("UploadVideoStream failed: %v", err)
	}

	_ = stream.Send(&ingestv1.UploadVideoChunk{
		Payload: &ingestv1.UploadVideoChunk_Header{
			Header: &ingestv1.UploadVideoHeader{
				MissionId:       "mission-201",
				FlightSessionId: "session-201",
				SegmentIndex:    0,
				Sha256Hex:       sha256Hex,
				TotalBytes:      uint64(len(payloadData)),
				Producer:        "edge-kit/1.3.2",
			},
		},
	})
	_ = stream.Send(&ingestv1.UploadVideoChunk{
		Payload: &ingestv1.UploadVideoChunk_ChunkData{
			ChunkData: payloadData,
		},
	})
	_, err = stream.CloseAndRecv()
	if err != nil {
		t.Fatalf("UploadVideoStream CloseAndRecv failed: %v", err)
	}

	// 3. GetUploadOffset -> expect full committed size
	offsetResp, err := client.GetUploadOffset(ctx, &ingestv1.GetUploadOffsetRequest{
		MissionId:    "mission-201",
		SegmentIndex: 0,
		Sha256Hex:    sha256Hex,
	})
	if err != nil {
		t.Fatalf("GetUploadOffset failed: %v", err)
	}
	if offsetResp.GetCommittedBytes() != uint64(len(payloadData)) {
		t.Errorf("got committed_bytes=%d, want %d", offsetResp.GetCommittedBytes(), len(payloadData))
	}

	// 4. FinalizeIngest after upload -> expect success
	finResp, err := client.FinalizeIngest(ctx, &ingestv1.FinalizeIngestRequest{
		MissionId:       "mission-201",
		FlightSessionId: "session-201",
		SegmentIndices:  []uint32{0},
		Preset:          "standard",
	})
	if err != nil {
		t.Fatalf("FinalizeIngest failed: %v", err)
	}
	if finResp.GetRunId() == "" || finResp.GetTemporalWorkflowId() == "" {
		t.Errorf("expected non-empty run_id and temporal_workflow_id, got run_id=%s, wf=%s", finResp.GetRunId(), finResp.GetTemporalWorkflowId())
	}
}
