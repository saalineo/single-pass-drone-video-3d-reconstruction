package reconstruction

import (
	"testing"
)

func TestComputeInputHash_Determinism(t *testing.T) {
	uris1 := []string{"s3://bucket/b.mp4", "s3://bucket/a.mp4"}
	params1 := map[string]string{"preset": "standard", "memory_hint": "gpu-standard"}

	// Reordered URIs and params
	uris2 := []string{"s3://bucket/a.mp4", "s3://bucket/b.mp4"}
	params2 := map[string]string{"memory_hint": "gpu-standard", "preset": "standard"}

	hash1 := ComputeInputHash(uris1, params1)
	hash2 := ComputeInputHash(uris2, params2)

	if hash1 != hash2 {
		t.Errorf("expected deterministic hash match, got %s != %s", hash1, hash2)
	}

	if len(hash1) != 64 {
		t.Errorf("expected 64 char hex string, got len %d", len(hash1))
	}
}

func TestComputeInputHash_Sensitivity(t *testing.T) {
	uris1 := []string{"s3://bucket/a.mp4"}
	params1 := map[string]string{"preset": "standard"}

	uris2 := []string{"s3://bucket/a.mp4"}
	params2 := map[string]string{"preset": "fast-preview"}

	hash1 := ComputeInputHash(uris1, params1)
	hash2 := ComputeInputHash(uris2, params2)

	if hash1 == hash2 {
		t.Errorf("expected different hashes for different params, got identical: %s", hash1)
	}
}
