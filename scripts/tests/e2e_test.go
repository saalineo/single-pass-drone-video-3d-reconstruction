package main

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/minio/minio-go/v7"
	ingestv1 "github.com/single-pass-recon/ingest-svc/gen/ingest/v1"
	ingestserver "github.com/single-pass-recon/ingest-svc/server"
	telemetryv1 "github.com/single-pass-recon/telemetry-worker/gen/telemetry/v1"
	telemetrypkg "github.com/single-pass-recon/telemetry-worker/pkg/telemetry"
	recon "github.com/single-pass-recon/workflows/reconstruction"
	"github.com/stretchr/testify/mock"
	"go.temporal.io/sdk/activity"
	"go.temporal.io/sdk/testsuite"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type mockS3Client struct {
	mu      sync.Mutex
	objects map[string][]byte
}

func newMockS3Client() *mockS3Client {
	return &mockS3Client{objects: make(map[string][]byte)}
}

func (m *mockS3Client) PutObject(ctx context.Context, bucketName, objectName string, reader io.Reader, objectSize int64, opts minio.PutObjectOptions) (minio.UploadInfo, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	data, _ := io.ReadAll(reader)
	m.objects[objectName] = data
	return minio.UploadInfo{Key: objectName, Size: int64(len(data))}, nil
}

func (m *mockS3Client) CopyObject(ctx context.Context, dst minio.CopyDestOptions, src minio.CopySrcOptions) (minio.UploadInfo, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	data, exists := m.objects[src.Object]
	if !exists {
		return minio.UploadInfo{}, minio.ErrorResponse{Code: "NoSuchKey"}
	}
	m.objects[dst.Object] = data
	return minio.UploadInfo{Key: dst.Object, Size: int64(len(data))}, nil
}

func (m *mockS3Client) RemoveObject(ctx context.Context, bucketName, objectName string, opts minio.RemoveObjectOptions) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.objects, objectName)
	return nil
}

func (m *mockS3Client) GetObject(ctx context.Context, bucketName, objectName string, opts minio.GetObjectOptions) (io.ReadCloser, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	data, exists := m.objects[objectName]
	if !exists {
		return nil, minio.ErrorResponse{Code: "NoSuchKey"}
	}
	return io.NopCloser(bytes.NewReader(data)), nil
}

func (m *mockS3Client) StatObject(ctx context.Context, bucketName, objectName string, opts minio.StatObjectOptions) (minio.ObjectInfo, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	data, exists := m.objects[objectName]
	if !exists {
		return minio.ObjectInfo{}, minio.ErrorResponse{Code: "NoSuchKey"}
	}
	return minio.ObjectInfo{Key: objectName, Size: int64(len(data))}, nil
}

type mockLauncher struct {
	mu       sync.Mutex
	launched map[string]string // missionID -> runID
}

func newMockLauncher() *mockLauncher {
	return &mockLauncher{launched: make(map[string]string)}
}

func (l *mockLauncher) LaunchReconstruction(ctx context.Context, missionID, flightSessionID, preset string, segmentIndices []uint32) (string, string, error) {
	l.mu.Lock()
	defer l.mu.Unlock()

	existingRunID, exists := l.launched[missionID]
	if exists {
		return existingRunID, "recon-" + existingRunID, nil
	}

	runID := uuid.New().String()
	l.launched[missionID] = runID
	return runID, "recon-" + runID, nil
}

func TestE2EControlPlane(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	s3 := newMockS3Client()
	launcher := newMockLauncher()
	videoStore := ingestserver.NewVideoStore(s3, "recon-raw")

	ingestLis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen for ingest-svc: %v", err)
	}
	ingestAddr := ingestLis.Addr().String()

	ingestServer := grpc.NewServer()
	ingestSrv := ingestserver.NewIngestServer(videoStore, launcher)
	ingestv1.RegisterIngestServiceServer(ingestServer, ingestSrv)

	go func() {
		_ = ingestServer.Serve(ingestLis)
	}()
	defer ingestServer.Stop()

	ingestConn, err := grpc.DialContext(ctx, ingestAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatalf("dial ingest: %v", err)
	}
	defer ingestConn.Close()
	ingestClient := ingestv1.NewIngestServiceClient(ingestConn)

	missionID := "mission-e2e-pass-1"
	videoPath := "testdata/fake_segment.mp4"

	// Upload Video Segment 0
	shaHex, bytesUploaded := uploadSegment(ctx, ingestClient, missionID, videoPath, 0)
	if bytesUploaded == 0 {
		t.Fatalf("expected non-zero bytes uploaded")
	}

	// Verify committed object in MinIO mock store
	expectedVideoPath := "missions/" + missionID + "/raw/video/00000.mp4"
	expectedMarkerPath := expectedVideoPath + ".sha256"

	if _, exists := s3.objects[expectedVideoPath]; !exists {
		t.Errorf("expected video object %s to exist in S3", expectedVideoPath)
	}
	if _, exists := s3.objects[expectedMarkerPath]; !exists {
		t.Errorf("expected video commit marker %s to exist in S3", expectedMarkerPath)
	}

	// Verify commit marker payload
	markerData := s3.objects[expectedMarkerPath]
	var markerMap map[string]interface{}
	if err := json.Unmarshal(markerData, &markerMap); err != nil {
		t.Errorf("failed to parse commit marker json: %v", err)
	}
	if markerMap["sha256"] != shaHex {
		t.Errorf("expected marker sha256 %s, got %v", shaHex, markerMap["sha256"])
	}

	// Finalize Ingest & Trigger Temporal Workflow
	runID, workflowID := finalizeIngest(ctx, ingestClient, missionID, "standard")
	if runID == "" || workflowID == "" {
		t.Fatalf("expected non-empty run_id and workflow_id")
	}
	if workflowID != "recon-"+runID {
		t.Errorf("expected workflow ID recon-%s, got %s", runID, workflowID)
	}

	// Idempotency Re-run
	reUploadSha, _ := uploadSegment(ctx, ingestClient, missionID, videoPath, 0)
	if reUploadSha != shaHex {
		t.Errorf("expected deduplicated sha match %s, got %s", shaHex, reUploadSha)
	}

	reRunID, reWfID := finalizeIngest(ctx, ingestClient, missionID, "standard")
	if reRunID != runID || reWfID != workflowID {
		t.Errorf("idempotency fail: expected run_id=%s wf=%s, got run_id=%s wf=%s", runID, workflowID, reRunID, reWfID)
	}

	//  Telemetry Leg Assertion
	telemStore := telemetrypkg.NewTelemetryStore(s3, "recon-raw")
	telemBuf := telemetrypkg.NewWindowBuffer()
	telemSeen := telemetrypkg.NewSeenSet(1000)

	telemMsg := &telemetryv1.DroneTelemetry{
		MissionId:       missionID,
		FlightSessionId: "session-e2e-01",
		Ts:              timestamppb.New(time.Unix(1700000000, 0)),
		Reading: &telemetryv1.DroneTelemetry_Gps{
			Gps: &telemetryv1.GPSReading{Lat: 45.0, Lon: -120.0, AltM: 100.0},
		},
	}
	telemBytes, _ := proto.Marshal(telemMsg)

	telemBuf.Add(missionID, "gps", telemetrypkg.Reading{
		MissionID: missionID,
		TS:        telemMsg.Ts.AsTime().UnixNano(),
		Sensor:    "gps",
		Payload:   telemBytes,
	})

	telemetrypkg.FlushOnce(ctx, telemBuf, telemStore, telemSeen, 1700000000)

	telemObj := "missions/" + missionID + "/raw/telemetry/gps/1700000000.jsonl"
	telemManifest := "missions/" + missionID + "/raw/telemetry/gps/manifest.json"

	if _, exists := s3.objects[telemObj]; !exists {
		t.Errorf("expected telemetry object %s to exist", telemObj)
	}
	if _, exists := s3.objects[telemManifest]; !exists {
		t.Errorf("expected telemetry manifest %s to exist", telemManifest)
	}
}

func dummyActivity(ctx context.Context, in recon.StageInput) (recon.StageOutput, error) {
	return recon.StageOutput{}, nil
}

func TestWorkflowStallGracefullyWithoutCVWorker(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestWorkflowEnvironment()

	env.RegisterActivityWithOptions(dummyActivity, activity.RegisterOptions{Name: recon.ActivityCuration})

	env.OnActivity(recon.ActivityCuration, mock.Anything, mock.Anything).Return(
		recon.StageOutput{}, nil,
	)

	input := recon.ReconstructionWorkflowInput{
		MissionID:        "m-stall-test",
		RunID:            "r-stall-test",
		Preset:           "standard",
		InputManifestURI: "s3://recon-raw/missions/m-stall-test/raw/video/manifest.json",
	}

	env.ExecuteWorkflow(recon.ReconstructionWorkflow, input)

	if !env.IsWorkflowCompleted() {
		t.Fatalf("expected workflow execution to finish in test env")
	}
}
