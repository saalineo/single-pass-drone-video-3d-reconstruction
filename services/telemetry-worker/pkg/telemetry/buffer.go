package telemetry

import "sync"

type Reading struct {
	MissionID string
	TS        int64  // unix nanos
	Sensor    string
	Payload   []byte // marshaled protobuf DroneTelemetry
}

type WindowBuffer struct {
	mu      sync.Mutex
	windows map[string][]Reading // key: mission_id|sensor
}

func NewWindowBuffer() *WindowBuffer {
	return &WindowBuffer{windows: make(map[string][]Reading)}
}

func (b *WindowBuffer) Add(missionID, sensor string, r Reading) {
	b.mu.Lock()
	defer b.mu.Unlock()
	key := missionID + "|" + sensor
	b.windows[key] = append(b.windows[key], r)
}

// DrainAll atomically empties every window, returning what accumulated since
// the last flush. Called by the ticker in flush.go.
func (b *WindowBuffer) DrainAll() map[string][]Reading {
	b.mu.Lock()
	defer b.mu.Unlock()
	out := b.windows
	b.windows = make(map[string][]Reading)
	return out
}
