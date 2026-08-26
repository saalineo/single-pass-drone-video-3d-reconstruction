package server

import (
	"log/slog"

	ingestv1 "github.com/single-pass-recon/ingest-svc/gen/ingest/v1"
)

type IngestServer struct {
	ingestv1.UnimplementedIngestServiceServer
	log *slog.Logger
}

func NewIngestServer(log *slog.Logger) *IngestServer {
	return &IngestServer{log: log}
}

func (s *IngestServer) UploadSession(stream ingestv1.IngestService_UploadSessionServer) error {
	received := map[string]uint64{}

	for {
		chunk, err := stream.Recv()
		if err != nil {
			return err
		}

		received[chunk.GetSegmentId()] += uint64(len(chunk.GetData()))
		s.log.Info("chunk received",
			"mission_id", chunk.GetMissionId(),
			"segment_id", chunk.GetSegmentId(),
			"offset", chunk.GetChunkOffset(),
		)

		if err := stream.Send(&ingestv1.UploadAck{
			SegmentId:     chunk.GetSegmentId(),
			BytesReceived: received[chunk.GetSegmentId()],
			Committed:     false,
		}); err != nil {
			return err
		}
	}
}
