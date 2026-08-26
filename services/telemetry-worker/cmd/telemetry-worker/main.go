package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
	telemetryv1 "github.com/single-pass-recon/telemetry-worker/gen/telemetry/v1"
	"github.com/single-pass-recon/telemetry-worker/pkg/telemetry"
	"google.golang.org/protobuf/proto"
)

func getEnvOrDefault(key, fallback string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return fallback
}

func sensorFromSubject(subject string) string {
	parts := strings.Split(subject, ".")
	if len(parts) >= 4 {
		return parts[len(parts)-1]
	}
	return "telemetry"
}

func main() {
	natsURL := getEnvOrDefault("NATS_URL", "nats://localhost:4222")
	streamName := getEnvOrDefault("TELEMETRY_STREAM", "TELEMETRY_DRONE")
	consumerName := getEnvOrDefault("TELEMETRY_CONSUMER", "telemetry-worker")

	s3Endpoint := getEnvOrDefault("S3_ENDPOINT", "localhost:9000")
	s3AccessKey := getEnvOrDefault("S3_ACCESS_KEY", "minioadmin")
	s3SecretKey := getEnvOrDefault("S3_SECRET_KEY", "minioadmin")
	s3UseSSL, _ := strconv.ParseBool(getEnvOrDefault("S3_SSL", "false"))
	bucketName := getEnvOrDefault("TELEMETRY_BUCKET", "recon-raw")

	dedupCapacityStr := getEnvOrDefault("TELEMETRY_DEDUP_CAPACITY", "50000")
	dedupCap, _ := strconv.Atoi(dedupCapacityStr)

	flushIntervalStr := getEnvOrDefault("TELEMETRY_FLUSH_INTERVAL", "5s")
	flushInterval, err := time.ParseDuration(flushIntervalStr)
	if err != nil {
		flushInterval = 5 * time.Second
	}

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	// MinIO client setup
	minioClient, err := minio.New(s3Endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(s3AccessKey, s3SecretKey, ""),
		Secure: s3UseSSL,
	})
	if err != nil {
		log.Fatalf("minio client error: %v", err)
	}

	// NATS setup
	nc, err := nats.Connect(natsURL)
	if err != nil {
		log.Fatalf("nats connect error: %v", err)
	}
	defer nc.Close()

	js, err := jetstream.New(nc)
	if err != nil {
		log.Fatalf("jetstream error: %v", err)
	}

	cons, err := telemetry.NewDurableConsumer(ctx, js, streamName, consumerName)
	if err != nil {
		log.Fatalf("consumer setup error: %v", err)
	}

	buf := telemetry.NewWindowBuffer()
	store := telemetry.NewTelemetryStore(&telemetry.MinioWrapper{Client: minioClient}, bucketName)
	seen := telemetry.NewSeenSet(dedupCap)

	go telemetry.RunFlushLoop(ctx, buf, store, seen, flushInterval)

	log.Printf("telemetry-worker started (stream: %s, consumer: %s)", streamName, consumerName)

	iter, err := cons.Messages()
	if err != nil {
		log.Fatalf("messages iterator error: %v", err)
	}
	defer iter.Stop()

	for {
		msg, err := iter.Next()
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			continue
		}

		var t telemetryv1.DroneTelemetry
		if err := proto.Unmarshal(msg.Data(), &t); err != nil {
			log.Printf("malformed message on %s, terminating: %v", msg.Subject(), err)
			_ = msg.Term() // poison message, terminate delivery
			continue
		}

		sensor := sensorFromSubject(msg.Subject())
		var ts int64
		if t.GetTs() != nil {
			ts = t.GetTs().AsTime().UnixNano()
		} else {
			ts = time.Now().UnixNano()
		}

		buf.Add(t.GetMissionId(), sensor, telemetry.Reading{
			MissionID: t.GetMissionId(),
			TS:        ts,
			Sensor:    sensor,
			Payload:   msg.Data(),
		})

		_ = msg.Ack()
	}
}
