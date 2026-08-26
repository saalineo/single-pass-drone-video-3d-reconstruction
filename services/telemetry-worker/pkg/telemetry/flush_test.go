package telemetry

import (
	"context"
	"testing"
)

func TestFlushOnce_Deduping(t *testing.T) {
	mockStore := newMockObjectStore()
	ts := NewTelemetryStore(mockStore, "recon-raw")
	seen := NewSeenSet(1000)
	buf := NewWindowBuffer()

	r1 := Reading{MissionID: "m1", TS: 1000, Sensor: "gps", Payload: []byte("p1")}
	r2 := Reading{MissionID: "m1", TS: 1000, Sensor: "gps", Payload: []byte("p1-dup")} // duplicate TS!

	buf.Add("m1", "gps", r1)
	buf.Add("m1", "gps", r2)

	FlushOnce(context.Background(), buf, ts, seen, 1700000000)

	objName := "missions/m1/raw/telemetry/gps/1700000000.jsonl"
	content, exists := mockStore.objects[objName]
	if !exists {
		t.Fatalf("expected object %s to exist", objName)
	}

	lines := 0
	for _, b := range content {
		if b == '\n' {
			lines++
		}
	}
	if lines != 1 {
		t.Errorf("expected 1 line after dedup, got %d", lines)
	}
}
