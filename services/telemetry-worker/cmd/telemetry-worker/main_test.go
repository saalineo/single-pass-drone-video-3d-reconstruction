package main

import (
	"context"
	"io"
	"sync"
	"testing"
	"time"

	"github.com/minio/minio-go/v7"
	telemetryv1 "github.com/single-pass-recon/telemetry-worker/gen/telemetry/v1"
	"github.com/single-pass-recon/telemetry-worker/pkg/telemetry"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type mockStoreClient struct {
	mu      sync.Mutex
	objects map[string][]byte
}

func newMockStoreClient() *mockStoreClient {
	return &mockStoreClient{objects: make(map[string][]byte)}
}

func (m *mockStoreClient) PutObject(ctx context.Context, bucketName, objectName string, reader io.Reader, objectSize int64, opts minio.PutObjectOptions) (minio.UploadInfo, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	data, _ := io.ReadAll(reader)
	m.objects[objectName] = data
	return minio.UploadInfo{Key: objectName, Size: int64(len(data))}, nil
}

func (m *mockStoreClient) CopyObject(ctx context.Context, dst minio.CopyDestOptions, src minio.CopySrcOptions) (minio.UploadInfo, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	data, exists := m.objects[src.Object]
	if !exists {
		return minio.UploadInfo{}, minio.ErrorResponse{Code: "NoSuchKey"}
	}
	m.objects[dst.Object] = data
	return minio.UploadInfo{Key: dst.Object, Size: int64(len(data))}, nil
}

func (m *mockStoreClient) RemoveObject(ctx context.Context, bucketName, objectName string, opts minio.RemoveObjectOptions) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.objects, objectName)
	return nil
}

func (m *mockStoreClient) GetObject(ctx context.Context, bucketName, objectName string, opts minio.GetObjectOptions) (io.ReadCloser, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return nil, minio.ErrorResponse{Code: "NoSuchKey"}
}

func TestTelemetryIngestionEndToEnd(t *testing.T) {
	mockStore := newMockStoreClient()
	store := telemetry.NewTelemetryStore(mockStore, "recon-raw")
	buf := telemetry.NewWindowBuffer()
	seen := telemetry.NewSeenSet(1000)

	// Build synthetic telemetry message
	telem := &telemetryv1.DroneTelemetry{
		MissionId:       "mission-e2e-01",
		FlightSessionId: "session-01",
		Ts:              timestamppb.New(time.Unix(1700000000, 0)),
		Reading: &telemetryv1.DroneTelemetry_Gps{
			Gps: &telemetryv1.GPSReading{
				Lat:        37.7749,
				Lon:        -122.4194,
				AltM:       120.5,
				Hdop:       0.8,
				Satellites: 14,
			},
		},
	}

	payload, err := proto.Marshal(telem)
	if err != nil {
		t.Fatalf("failed to marshal telemetry: %v", err)
	}

	buf.Add(telem.MissionId, "gps", telemetry.Reading{
		MissionID: telem.MissionId,
		TS:        telem.Ts.AsTime().UnixNano(),
		Sensor:    "gps",
		Payload:   payload,
	})

	telemetry.FlushOnce(context.Background(), buf, store, seen, 1700000000)

	expectedObject := "missions/mission-e2e-01/raw/telemetry/gps/1700000000.jsonl"
	expectedMarker := expectedObject + ".sha256"
	expectedManifest := "missions/mission-e2e-01/raw/telemetry/gps/manifest.json"

	if _, exists := mockStore.objects[expectedObject]; !exists {
		t.Errorf("expected object %s to exist in object store", expectedObject)
	}
	if _, exists := mockStore.objects[expectedMarker]; !exists {
		t.Errorf("expected marker %s to exist in object store", expectedMarker)
	}
	if _, exists := mockStore.objects[expectedManifest]; !exists {
		t.Errorf("expected manifest %s to exist in object store", expectedManifest)
	}
}

func TestMalformedTelemetryRejection(t *testing.T) {
	malformed := []byte{0xFF, 0xFF, 0xFF}
	var telem telemetryv1.DroneTelemetry
	err := proto.Unmarshal(malformed, &telem)
	if err == nil {
		t.Fatalf("expected error when unmarshaling malformed byte slice, got nil")
	}
}
