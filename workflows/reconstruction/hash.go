package reconstruction

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"sort"
)

// ComputeInputHash must be a pure function of its arguments — no time.Now(),
// no randomness, no map iteration without sorting — because Temporal replays
// workflow code deterministically during history replay. A hash that varies
// between the original run and a replay would desync workflow state.
func ComputeInputHash(inputURIs []string, params map[string]string) string {
	sorted := append([]string(nil), inputURIs...)
	sort.Strings(sorted)

	keys := make([]string, 0, len(params))
	for k := range params {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	orderedParams := make([][2]string, 0, len(keys))
	for _, k := range keys {
		orderedParams = append(orderedParams, [2]string{k, params[k]})
	}

	payload, _ := json.Marshal(struct {
		URIs   []string    `json:"uris"`
		Params [][2]string `json:"params"`
	}{sorted, orderedParams})

	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:])
}
