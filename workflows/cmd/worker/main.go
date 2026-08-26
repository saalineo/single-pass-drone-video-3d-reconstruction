package main

import (
	"log"
	"os"

	"github.com/single-pass-recon/workflows/reconstruction"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/worker"
)

func getEnvOrDefault(key, fallback string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return fallback
}

func main() {
	hostPort := getEnvOrDefault("TEMPORAL_HOST_PORT", "temporal-frontend.recon-messaging.svc.cluster.local:7233")
	namespace := getEnvOrDefault("TEMPORAL_NAMESPACE", "recon")

	c, err := client.Dial(client.Options{
		HostPort:  hostPort,
		Namespace: namespace,
	})
	if err != nil {
		log.Fatalf("temporal client: %v", err)
	}
	defer c.Close()

	w := worker.New(c, reconstruction.ControlTaskQueue, worker.Options{})
	w.RegisterWorkflow(reconstruction.ReconstructionWorkflow)
	// Deliberately no w.RegisterActivity(...) calls here.
	// Activities are registered by Python workers on CV_TASK_QUEUE in Phase 3.

	log.Printf("workflow worker listening on task queue: %s (host: %s, ns: %s)", reconstruction.ControlTaskQueue, hostPort, namespace)
	if err := w.Run(worker.InterruptCh()); err != nil {
		log.Fatalf("worker run: %v", err)
	}
}
