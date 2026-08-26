package server

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"time"

	"github.com/minio/minio-go/v7"
)

var ErrHashMismatch = errors.New("hash mismatch")

type CommitMarker struct {
	SHA256        string    `json:"sha256"`
	Producer      string    `json:"producer"`
	WorkflowRunID string    `json:"workflow_run_id,omitempty"` // empty at ingest time
	SizeBytes     int64     `json:"size_bytes"`
	CommittedAt   time.Time `json:"committed_at"`
}

type VideoStore struct {
	client *minio.Client
	bucket string // "recon-raw"
}

func NewVideoStore(c *minio.Client, bucket string) *VideoStore {
	if bucket == "" {
		bucket = "recon-raw"
	}
	return &VideoStore{client: c, bucket: bucket}
}

func (s *VideoStore) tempKey(missionID string, segment uint32) string {
	return fmt.Sprintf("missions/%s/.tmp/raw/video/%05d.mp4", missionID, segment)
}

func (s *VideoStore) finalKey(missionID string, segment uint32) string {
	return fmt.Sprintf("missions/%s/raw/video/%05d.mp4", missionID, segment)
}

func (s *VideoStore) markerKey(missionID string, segment uint32) string {
	return fmt.Sprintf("missions/%s/raw/video/%05d.mp4.sha256", missionID, segment)
}

func (s *VideoStore) FinalObjectURI(missionID string, segment uint32) string {
	return fmt.Sprintf("s3://%s/%s", s.bucket, s.finalKey(missionID, segment))
}

// Committed reports whether a segment is already durably committed with the
// given hash — the ingest-time idempotency check.
func (s *VideoStore) Committed(ctx context.Context, missionID string, segment uint32, sha256Hex string) (bool, error) {
	obj, err := s.client.GetObject(ctx, s.bucket, s.markerKey(missionID, segment), minio.GetObjectOptions{})
	if err != nil {
		return false, nil // no marker => not committed
	}
	defer obj.Close()
	var m CommitMarker
	if err := json.NewDecoder(obj).Decode(&m); err != nil {
		return false, nil // unreadable marker => treat as not committed, re-upload
	}
	return m.SHA256 == sha256Hex, nil
}

// IsSegmentCommitted checks if any commit marker exists for the given segment.
func (s *VideoStore) IsSegmentCommitted(ctx context.Context, missionID string, segment uint32) (bool, error) {
	obj, err := s.client.GetObject(ctx, s.bucket, s.markerKey(missionID, segment), minio.GetObjectOptions{})
	if err != nil {
		return false, nil
	}
	defer obj.Close()
	var m CommitMarker
	if err := json.NewDecoder(obj).Decode(&m); err != nil {
		return false, nil
	}
	return m.SHA256 != "", nil
}

// GetCommittedBytes returns the number of committed bytes for a segment.
func (s *VideoStore) GetCommittedBytes(ctx context.Context, missionID string, segment uint32, sha256Hex string) (uint64, error) {
	obj, err := s.client.GetObject(ctx, s.bucket, s.markerKey(missionID, segment), minio.GetObjectOptions{})
	if err == nil {
		defer obj.Close()
		var m CommitMarker
		if err := json.NewDecoder(obj).Decode(&m); err == nil && m.SHA256 == sha256Hex {
			return uint64(m.SizeBytes), nil
		}
	}

	stat, err := s.client.StatObject(ctx, s.bucket, s.tempKey(missionID, segment), minio.StatObjectOptions{})
	if err == nil {
		return uint64(stat.Size), nil
	}

	return 0, nil
}

// StageAndCommit streams r into the temp prefix, verifies the hash, then does
// a server-side copy into the final immutable key and writes the commit
// marker. The temp object is deleted only after the marker write succeeds.
func (s *VideoStore) StageAndCommit(ctx context.Context, missionID string, segment uint32, producer, declaredSHA256 string, r io.Reader, size int64) (objectURI string, err error) {
	tmp := s.tempKey(missionID, segment)
	final := s.finalKey(missionID, segment)

	hasher := sha256.New()
	tee := io.TeeReader(r, hasher)

	if _, err = s.client.PutObject(ctx, s.bucket, tmp, tee, size, minio.PutObjectOptions{
		ContentType: "video/mp4",
	}); err != nil {
		return "", fmt.Errorf("stage upload: %w", err)
	}

	actual := hex.EncodeToString(hasher.Sum(nil))
	if actual != declaredSHA256 {
		_ = s.client.RemoveObject(ctx, s.bucket, tmp, minio.RemoveObjectOptions{})
		return "", fmt.Errorf("%w: declared=%s actual=%s", ErrHashMismatch, declaredSHA256, actual)
	}

	src := minio.CopySrcOptions{Bucket: s.bucket, Object: tmp}
	dst := minio.CopyDestOptions{Bucket: s.bucket, Object: final}
	if _, err = s.client.CopyObject(ctx, dst, src); err != nil {
		return "", fmt.Errorf("commit copy: %w", err)
	}

	marker := CommitMarker{
		SHA256:      actual,
		Producer:    producer,
		SizeBytes:   size,
		CommittedAt: time.Now().UTC(),
	}
	body, _ := json.Marshal(marker)
	if _, err = s.client.PutObject(ctx, s.bucket, s.markerKey(missionID, segment), bytes.NewReader(body), int64(len(body)), minio.PutObjectOptions{ContentType: "application/json"}); err != nil {
		return "", fmt.Errorf("commit marker: %w", err)
	}

	_ = s.client.RemoveObject(ctx, s.bucket, tmp, minio.RemoveObjectOptions{})
	return s.FinalObjectURI(missionID, segment), nil
}
