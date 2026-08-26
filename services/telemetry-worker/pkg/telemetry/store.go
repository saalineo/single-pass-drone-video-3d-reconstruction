package telemetry

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"

	"github.com/minio/minio-go/v7"
)

type ObjectStoreClient interface {
	PutObject(ctx context.Context, bucketName, objectName string, reader io.Reader, objectSize int64, opts minio.PutObjectOptions) (minio.UploadInfo, error)
	CopyObject(ctx context.Context, dst minio.CopyDestOptions, src minio.CopySrcOptions) (minio.UploadInfo, error)
	RemoveObject(ctx context.Context, bucketName, objectName string, opts minio.RemoveObjectOptions) error
	GetObject(ctx context.Context, bucketName, objectName string, opts minio.GetObjectOptions) (io.ReadCloser, error)
}

type MinioWrapper struct {
	*minio.Client
}

func (w *MinioWrapper) GetObject(ctx context.Context, bucketName, objectName string, opts minio.GetObjectOptions) (io.ReadCloser, error) {
	return w.Client.GetObject(ctx, bucketName, objectName, opts)
}

type TelemetryStore struct {
	client ObjectStoreClient
	bucket string
}

func NewTelemetryStore(client ObjectStoreClient, bucket string) *TelemetryStore {
	if bucket == "" {
		bucket = "recon-raw"
	}
	return &TelemetryStore{
		client: client,
		bucket: bucket,
	}
}

type Manifest struct {
	MissionID   string   `json:"mission_id"`
	Sensor      string   `json:"sensor"`
	WindowKeys  []string `json:"window_keys"`
	LastUpdated int64    `json:"last_updated"`
}

func (s *TelemetryStore) CommitWindow(ctx context.Context, key string, windowStart int64, readings []Reading) error {
	if len(readings) == 0 {
		return nil
	}

	missionID, sensor := SplitKey(key)

	var buf bytes.Buffer
	for _, r := range readings {
		line, _ := json.Marshal(r)
		buf.Write(line)
		buf.WriteByte('\n')
	}
	content := buf.Bytes()
	hash := sha256.Sum256(content)
	shaHex := hex.EncodeToString(hash[:])

	objectName := fmt.Sprintf("missions/%s/raw/telemetry/%s/%010d.jsonl", missionID, sensor, windowStart)
	tmpName := fmt.Sprintf("missions/%s/.tmp/telemetry/%s/%010d.jsonl", missionID, sensor, windowStart)

	// Upload to .tmp
	_, err := s.client.PutObject(ctx, s.bucket, tmpName, bytes.NewReader(content), int64(len(content)), minio.PutObjectOptions{
		ContentType: "application/jsonlines",
	})
	if err != nil {
		return fmt.Errorf("put tmp telemetry: %w", err)
	}

	// Atomic copy to target path
	_, err = s.client.CopyObject(ctx,
		minio.CopyDestOptions{Bucket: s.bucket, Object: objectName},
		minio.CopySrcOptions{Bucket: s.bucket, Object: tmpName},
	)
	if err != nil {
		return fmt.Errorf("copy telemetry object: %w", err)
	}

	// Write commit marker
	markerName := objectName + ".sha256"
	markerPayload, _ := json.Marshal(map[string]interface{}{
		"sha256":    shaHex,
		"size":      len(content),
		"count":     len(readings),
		"timestamp": windowStart,
	})
	_, err = s.client.PutObject(ctx, s.bucket, markerName, bytes.NewReader(markerPayload), int64(len(markerPayload)), minio.PutObjectOptions{
		ContentType: "application/json",
	})
	if err != nil {
		return fmt.Errorf("write telemetry commit marker: %w", err)
	}

	// Cleanup .tmp
	_ = s.client.RemoveObject(ctx, s.bucket, tmpName, minio.RemoveObjectOptions{})

	// Update manifest
	return s.updateManifest(ctx, missionID, sensor, objectName, windowStart)
}

func (s *TelemetryStore) updateManifest(ctx context.Context, missionID, sensor, newObject string, windowStart int64) error {
	manifestPath := fmt.Sprintf("missions/%s/raw/telemetry/%s/manifest.json", missionID, sensor)

	manifest := Manifest{
		MissionID:   missionID,
		Sensor:      sensor,
		WindowKeys:  []string{},
		LastUpdated: windowStart,
	}

	obj, err := s.client.GetObject(ctx, s.bucket, manifestPath, minio.GetObjectOptions{})
	if err == nil && obj != nil {
		var existing Manifest
		if err := json.NewDecoder(obj).Decode(&existing); err == nil {
			manifest.WindowKeys = existing.WindowKeys
		}
		_ = obj.Close()
	}

	found := false
	for _, k := range manifest.WindowKeys {
		if k == newObject {
			found = true
			break
		}
	}
	if !found {
		manifest.WindowKeys = append(manifest.WindowKeys, newObject)
	}
	manifest.LastUpdated = windowStart

	manifestBytes, _ := json.Marshal(manifest)
	_, err = s.client.PutObject(ctx, s.bucket, manifestPath, bytes.NewReader(manifestBytes), int64(len(manifestBytes)), minio.PutObjectOptions{
		ContentType: "application/json",
	})
	if err != nil {
		return fmt.Errorf("update manifest: %w", err)
	}
	return nil
}

func SplitKey(key string) (missionID, sensor string) {
	for i := 0; i < len(key); i++ {
		if key[i] == '|' {
			return key[:i], key[i+1:]
		}
	}
	return key, "unknown"
}
