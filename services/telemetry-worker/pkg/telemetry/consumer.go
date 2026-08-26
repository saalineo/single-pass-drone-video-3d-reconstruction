package telemetry

import (
	"context"
	"time"

	"github.com/nats-io/nats.go/jetstream"
)

// NewDurableConsumer creates (or binds to) a durable pull consumer. Explicit
// ack is mandatory: a message is acked only after its reading is folded into
// an in-memory window AND that window has been flushed and committed to
// MinIO at least once. If the process crashes between receipt and flush,
// JetStream redelivers on restart — at-least-once, matching doc 04 §4.
func NewDurableConsumer(ctx context.Context, js jetstream.JetStream, streamName, consumerName string) (jetstream.Consumer, error) {
	if streamName == "" {
		streamName = "TELEMETRY_DRONE"
	}
	if consumerName == "" {
		consumerName = "telemetry-worker"
	}

	return js.CreateOrUpdateConsumer(ctx, streamName, jetstream.ConsumerConfig{
		Durable:       consumerName,
		FilterSubject: "telemetry.drone.>",
		AckPolicy:     jetstream.AckExplicitPolicy,
		AckWait:       15 * time.Second, // must exceed one flush cycle (5s) with margin
		MaxAckPending: 5000,             // backpressure valve at 10 Hz per sensor per mission
		DeliverPolicy: jetstream.DeliverAllPolicy,
	})
}
