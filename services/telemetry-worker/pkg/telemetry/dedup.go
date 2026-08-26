package telemetry

import (
	"crypto/sha256"
	"encoding/hex"
	"strconv"
	"sync"
)

// DedupKey mirrors the (mission_id, t, sensor) tuple used in dedup filtering.
// Nats-Msg-Id dedup window (2m, step 1) already filters most republish
// duplicates before they reach us; this is a second, defensive layer that
// also catches duplicates that arrive more than 2 minutes apart (e.g. an
// edge kit replaying a store-and-forward queue after a long datalink outage,
// or duplicates crossing a JetStream stream restart).
func DedupKey(missionID, sensor string, tsUnixNano int64) string {
	h := sha256.Sum256([]byte(missionID + "|" + sensor + "|" + strconv.FormatInt(tsUnixNano, 10)))
	return hex.EncodeToString(h[:])
}

type SeenSet struct {
	mu       sync.Mutex
	capacity int
	entries  map[string]struct{}
	queue    []string
}

func NewSeenSet(capacity int) *SeenSet {
	if capacity <= 0 {
		capacity = 50000
	}
	return &SeenSet{
		capacity: capacity,
		entries:  make(map[string]struct{}, capacity),
		queue:    make([]string, 0, capacity),
	}
}

func (s *SeenSet) SeenRecently(key string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	_, exists := s.entries[key]
	return exists
}

func (s *SeenSet) Mark(key string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.entries[key]; exists {
		return
	}
	if len(s.queue) >= s.capacity {
		oldest := s.queue[0]
		s.queue = s.queue[1:]
		delete(s.entries, oldest)
	}
	s.entries[key] = struct{}{}
	s.queue = append(s.queue, key)
}
