package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"

	ingestv1 "github.com/single-pass-recon/ingest-svc/gen/ingest/v1"
	missionv1 "github.com/single-pass-recon/mission-svc/gen/mission/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type MockResult struct {
	MissionID          string `json:"mission_id"`
	RunID              string `json:"run_id"`
	TemporalWorkflowID string `json:"temporal_workflow_id"`
	Sha256             string `json:"sha256"`
	BytesUploaded      uint64 `json:"bytes_uploaded"`
}

func main() {
	missionAddr := flag.String("mission-addr", "localhost:50051", "mission-svc gRPC address")
	ingestAddr := flag.String("ingest-addr", "localhost:50052", "ingest-svc gRPC address")
	videoFile := flag.String("video", "scripts/tests/testdata/fake_segment.mp4", "video segment file path")
	preset := flag.String("preset", "standard", "reconstruction preset")
	existingMissionID := flag.String("mission-id", "", "optional existing mission ID to reuse for idempotency testing")
	flag.Parse()

	ctx := context.Background()

	missionConn, err := grpc.NewClient(*missionAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("dial mission-svc: %v", err)
	}
	defer missionConn.Close()

	ingestConn, err := grpc.NewClient(*ingestAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("dial ingest-svc: %v", err)
	}
	defer ingestConn.Close()

	missionClient := missionv1.NewMissionServiceClient(missionConn)
	ingestClient := ingestv1.NewIngestServiceClient(ingestConn)

	missionID := *existingMissionID
	if missionID == "" {
		missionID = createMission(ctx, missionClient)
		log.Printf("mission created: %s", missionID)
	} else {
		log.Printf("reusing existing mission: %s", missionID)
	}

	sha, size := uploadSegment(ctx, ingestClient, missionID, *videoFile, 0)
	log.Printf("segment 0 upload complete: sha256=%s size=%d", sha, size)

	runID, workflowID := finalizeIngest(ctx, ingestClient, missionID, *preset)
	log.Printf("ingest finalized: run_id=%s workflow_id=%s", runID, workflowID)

	res := MockResult{
		MissionID:          missionID,
		RunID:              runID,
		TemporalWorkflowID: workflowID,
		Sha256:             sha,
		BytesUploaded:      size,
	}

	out, _ := json.MarshalIndent(res, "", "  ")
	fmt.Println(string(out))
}

func createMission(ctx context.Context, c missionv1.MissionServiceClient) string {
	resp, err := c.CreateMission(ctx, &missionv1.CreateMissionRequest{
		Name:                  fmt.Sprintf("e2e-mock-%d", os.Getpid()),
		AreaOfInterestGeojson: `{"type":"Polygon","coordinates":[[[0,0],[0,0.001],[0.001,0.001],[0.001,0],[0,0]]]}`,
		Classification:        "unclassified",
		ExpectedSensors:       []string{"rgb", "gnss"},
		OperatorId:            "e2e-mock-drone",
	})
	if err != nil {
		log.Fatalf("CreateMission: %v", err)
	}
	return resp.MissionId
}

func uploadSegment(ctx context.Context, c ingestv1.IngestServiceClient, missionID, path string, segment uint32) (string, uint64) {
	data, err := os.ReadFile(path)
	if err != nil {
		log.Fatalf("read testdata: %v", err)
	}
	sum := sha256.Sum256(data)
	shaHex := hex.EncodeToString(sum[:])

	stream, err := c.UploadVideoStream(ctx)
	if err != nil {
		log.Fatalf("open upload stream: %v", err)
	}

	if err := stream.Send(&ingestv1.UploadVideoChunk{
		Payload: &ingestv1.UploadVideoChunk_Header{Header: &ingestv1.UploadVideoHeader{
			MissionId:    missionID,
			SegmentIndex: segment,
			Sha256Hex:    shaHex,
			TotalBytes:   uint64(len(data)),
			Producer:     "e2e-mock-drone/0.1.0",
		}},
	}); err != nil {
		log.Fatalf("send header: %v", err)
	}

	const chunkSize = 4 << 20 // 4 MiB
	for off := 0; off < len(data); off += chunkSize {
		end := off + chunkSize
		if end > len(data) {
			end = len(data)
		}
		if err := stream.Send(&ingestv1.UploadVideoChunk{
			Payload: &ingestv1.UploadVideoChunk_ChunkData{ChunkData: data[off:end]},
		}); err != nil {
			log.Fatalf("send chunk at offset %d: %v", off, err)
		}
	}

	resp, err := stream.CloseAndRecv()
	if err != nil {
		log.Fatalf("close upload stream: %v", err)
	}
	if resp.Sha256Hex != shaHex {
		log.Fatalf("server-reported hash %s != client hash %s", resp.Sha256Hex, shaHex)
	}
	return resp.Sha256Hex, resp.BytesReceived
}

func finalizeIngest(ctx context.Context, c ingestv1.IngestServiceClient, missionID, preset string) (string, string) {
	resp, err := c.FinalizeIngest(ctx, &ingestv1.FinalizeIngestRequest{
		MissionId:      missionID,
		SegmentIndices: []uint32{0},
		Preset:         preset,
	})
	if err != nil {
		log.Fatalf("FinalizeIngest: %v", err)
	}
	return resp.RunId, resp.TemporalWorkflowId
}
