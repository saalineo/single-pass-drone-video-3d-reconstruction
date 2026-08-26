package server

import (
	"bytes"
	"context"
	"encoding/hex"
	"errors"
	"fmt"
	"io"

	"github.com/google/uuid"
	ingestv1 "github.com/single-pass-recon/ingest-svc/gen/ingest/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

const maxSegmentBytes = 8 << 30 // 8 GiB guard rail

type WorkflowLauncher interface {
	LaunchReconstruction(ctx context.Context, missionID, flightSessionID, preset string, segmentIndices []uint32) (runID string, temporalWorkflowID string, err error)
}

type DefaultWorkflowLauncher struct{}

func (d *DefaultWorkflowLauncher) LaunchReconstruction(ctx context.Context, missionID, flightSessionID, preset string, segmentIndices []uint32) (string, string, error) {
	runID := uuid.New().String()
	workflowID := fmt.Sprintf("recon-%s", missionID)
	return runID, workflowID, nil
}

type IngestServer struct {
	ingestv1.UnimplementedIngestServiceServer
	store    *VideoStore
	launcher WorkflowLauncher
}

func NewIngestServer(store *VideoStore, launcher WorkflowLauncher) *IngestServer {
	if launcher == nil {
		launcher = &DefaultWorkflowLauncher{}
	}
	return &IngestServer{
		store:    store,
		launcher: launcher,
	}
}

func (s *IngestServer) UploadVideoStream(stream ingestv1.IngestService_UploadVideoStreamServer) error {
	ctx := stream.Context()

	first, err := stream.Recv()
	if err != nil {
		return status.Errorf(codes.InvalidArgument, "expected header as first message: %v", err)
	}
	hdr := first.GetHeader()
	if hdr == nil {
		return status.Error(codes.InvalidArgument, "first message must be UploadVideoHeader")
	}
	if _, err := hex.DecodeString(hdr.GetSha256Hex()); err != nil || len(hdr.GetSha256Hex()) != 64 {
		return status.Error(codes.InvalidArgument, "sha256_hex must be 64 hex chars")
	}
	if hdr.GetTotalBytes() > maxSegmentBytes {
		return status.Errorf(codes.InvalidArgument, "segment exceeds %d bytes", maxSegmentBytes)
	}

	if ok, _ := s.store.Committed(ctx, hdr.GetMissionId(), hdr.GetSegmentIndex(), hdr.GetSha256Hex()); ok {
		return stream.SendAndClose(&ingestv1.UploadVideoResponse{
			ObjectUri:     s.store.FinalObjectURI(hdr.GetMissionId(), hdr.GetSegmentIndex()),
			Sha256Hex:     hdr.GetSha256Hex(),
			BytesReceived: hdr.GetTotalBytes(),
			Deduplicated:  true,
		})
	}

	buf := &bytes.Buffer{}
	var received uint64
	for {
		msg, err := stream.Recv()
		if err == io.EOF {
			break
		}
		if err != nil {
			return status.Errorf(codes.Aborted, "stream recv: %v", err)
		}
		chunk := msg.GetChunkData()
		if chunk == nil {
			continue
		}
		received += uint64(len(chunk))
		if received > hdr.GetTotalBytes() {
			return status.Error(codes.InvalidArgument, "received more bytes than declared total_bytes")
		}
		if _, err := buf.Write(chunk); err != nil {
			return status.Errorf(codes.Internal, "buffer write: %v", err)
		}
	}
	if received != hdr.GetTotalBytes() {
		// corrupt/truncated segment -> quarantine, do
		// not commit. Client retries via GetUploadOffset + resume.
		return status.Errorf(codes.DataLoss, "truncated upload: got %d want %d", received, hdr.GetTotalBytes())
	}

	uri, err := s.store.StageAndCommit(ctx, hdr.GetMissionId(), hdr.GetSegmentIndex(), hdr.GetProducer(), hdr.GetSha256Hex(), buf, int64(buf.Len()))
	if err != nil {
		if errors.Is(err, ErrHashMismatch) {
			return status.Errorf(codes.DataLoss, "hash verification failed: %v", err)
		}
		return status.Errorf(codes.Internal, "commit: %v", err)
	}

	return stream.SendAndClose(&ingestv1.UploadVideoResponse{
		ObjectUri:     uri,
		Sha256Hex:     hdr.GetSha256Hex(),
		BytesReceived: received,
		Deduplicated:  false,
	})
}

func (s *IngestServer) GetUploadOffset(ctx context.Context, req *ingestv1.GetUploadOffsetRequest) (*ingestv1.GetUploadOffsetResponse, error) {
	if req.GetMissionId() == "" || req.GetSha256Hex() == "" {
		return nil, status.Error(codes.InvalidArgument, "mission_id and sha256_hex required")
	}
	bytesCommitted, err := s.store.GetCommittedBytes(ctx, req.GetMissionId(), req.GetSegmentIndex(), req.GetSha256Hex())
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get offset: %v", err)
	}
	return &ingestv1.GetUploadOffsetResponse{
		CommittedBytes: bytesCommitted,
	}, nil
}

func (s *IngestServer) FinalizeIngest(ctx context.Context, req *ingestv1.FinalizeIngestRequest) (*ingestv1.FinalizeIngestResponse, error) {
	if req.GetMissionId() == "" || len(req.GetSegmentIndices()) == 0 {
		return nil, status.Error(codes.InvalidArgument, "mission_id and non-empty segment_indices required")
	}

	for _, seg := range req.GetSegmentIndices() {
		ok, err := s.store.IsSegmentCommitted(ctx, req.GetMissionId(), seg)
		if err != nil || !ok {
			return nil, status.Errorf(codes.FailedPrecondition, "segment %d not committed", seg)
		}
	}

	runID, workflowID, err := s.launcher.LaunchReconstruction(ctx, req.GetMissionId(), req.GetFlightSessionId(), req.GetPreset(), req.GetSegmentIndices())
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to launch workflow: %v", err)
	}

	return &ingestv1.FinalizeIngestResponse{
		RunId:              runID,
		TemporalWorkflowId: workflowID,
	}, nil
}
