package telemetry

import "testing"

func TestDedupKey_Determinism(t *testing.T) {
	k1 := DedupKey("m1", "gps", 1700000000000000000)
	k2 := DedupKey("m1", "gps", 1700000000000000000)
	k3 := DedupKey("m1", "imu", 1700000000000000000)

	if k1 != k2 {
		t.Errorf("expected deterministic key match, got %s != %s", k1, k2)
	}
	if k1 == k3 {
		t.Errorf("expected different keys for different sensors")
	}
}

func TestSeenSet_LRUEviction(t *testing.T) {
	seen := NewSeenSet(2)

	seen.Mark("key1")
	seen.Mark("key2")

	if !seen.SeenRecently("key1") || !seen.SeenRecently("key2") {
		t.Fatalf("expected key1 and key2 to be seen")
	}

	// Exceed capacity
	seen.Mark("key3")

	if seen.SeenRecently("key1") {
		t.Errorf("expected key1 to be evicted")
	}
	if !seen.SeenRecently("key2") || !seen.SeenRecently("key3") {
		t.Errorf("expected key2 and key3 to remain in set")
	}
}
