package telemetry

import (
	"testing"
)

func TestWindowBuffer_AddAndDrain(t *testing.T) {
	buf := NewWindowBuffer()

	r1 := Reading{MissionID: "m1", TS: 100, Sensor: "gps", Payload: []byte("data1")}
	r2 := Reading{MissionID: "m1", TS: 200, Sensor: "gps", Payload: []byte("data2")}
	r3 := Reading{MissionID: "m1", TS: 150, Sensor: "imu", Payload: []byte("imu1")}

	buf.Add("m1", "gps", r1)
	buf.Add("m1", "gps", r2)
	buf.Add("m1", "imu", r3)

	drained := buf.DrainAll()

	if len(drained) != 2 {
		t.Errorf("expected 2 window keys, got %d", len(drained))
	}
	if len(drained["m1|gps"]) != 2 {
		t.Errorf("expected 2 gps readings, got %d", len(drained["m1|gps"]))
	}
	if len(drained["m1|imu"]) != 1 {
		t.Errorf("expected 1 imu reading, got %d", len(drained["m1|imu"]))
	}

	// Second drain should be empty
	empty := buf.DrainAll()
	if len(empty) != 0 {
		t.Errorf("expected empty drain after reset, got %d", len(empty))
	}
}
