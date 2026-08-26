package telemetry

import (
	"context"
	"io"
	"sync"
	"testing"

	"github.com/minio/minio-go/v7"
)

type mockObjectStore struct {
	mu      sync.Mutex
	objects map[string][]byte
}

func newMockObjectStore() *mockObjectStore {
	return &mockObjectStore{objects: make(map[string][]byte)}
}

func (m *mockObjectStore) PutObject(ctx context.Context, bucketName, objectName string, reader io.Reader, objectSize int64, opts minio.PutObjectOptions) (minio.UploadInfo, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	data, _ := io.ReadAll(reader)
	m.objects[objectName] = data
	return minio.UploadInfo{Key: objectName, Size: int64(len(data))}, nil
}

func (m *mockObjectStore) CopyObject(ctx context.Context, dst minio.CopyDestOptions, src minio.CopySrcOptions) (minio.UploadInfo, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	data, exists := m.objects[src.Object]
	if !exists {
		return minio.UploadInfo{}, minio.ErrorResponse{Code: "NoSuchKey"}
	}
	m.objects[dst.Object] = data
	return minio.UploadInfo{Key: dst.Object, Size: int64(len(data))}, nil
}

func (m *mockObjectStore) RemoveObject(ctx context.Context, bucketName, objectName string, opts minio.RemoveObjectOptions) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.objects, objectName)
	return nil
}

func (m *mockObjectStore) GetObject(ctx context.Context, bucketName, objectName string, opts minio.GetObjectOptions) (io.ReadCloser, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return nil, minio.ErrorResponse{Code: "NoSuchKey"}
}

func TestTelemetryStore_CommitWindow(t *testing.T) {
	mockStore := newMockObjectStore()
	ts := NewTelemetryStore(mockStore, "recon-raw")

	readings := []Reading{
		{MissionID: "m1", TS: 1000, Sensor: "gps", Payload: []byte("p1")},
		{MissionID: "m1", TS: 2000, Sensor: "gps", Payload: []byte("p2")},
	}

	err := ts.CommitWindow(context.Background(), "m1|gps", 1700000000, readings)
	if err != nil {
		t.Fatalf("expected commit window to succeed, got %v", err)
	}

	expectedObj := "missions/m1/raw/telemetry/gps/1700000000.jsonl"
	expectedMarker := expectedObj + ".sha256"
	expectedManifest := "missions/m1/raw/telemetry/gps/manifest.json"

	if _, exists := mockStore.objects[expectedObj]; !exists {
		t.Errorf("expected committed object %s to exist", expectedObj)
	}
	if _, exists := mockStore.objects[expectedMarker]; !exists {
		t.Errorf("expected commit marker %s to exist", expectedMarker)
	}
	if _, exists := mockStore.objects[expectedManifest]; !exists {
		t.Errorf("expected manifest %s to exist", expectedManifest)
	}
}
