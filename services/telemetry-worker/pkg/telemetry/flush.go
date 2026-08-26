package telemetry

import (
	"context"
	"log"
	"time"
)

func RunFlushLoop(ctx context.Context, buf *WindowBuffer, store *TelemetryStore, seen *SeenSet, interval time.Duration) {
	if interval <= 0 {
		interval = 5 * time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case windowStart := <-ticker.C:
			FlushOnce(ctx, buf, store, seen, windowStart.Unix())
		}
	}
}

func FlushOnce(ctx context.Context, buf *WindowBuffer, store *TelemetryStore, seen *SeenSet, windowUnix int64) {
	for key, readings := range buf.DrainAll() {
		missionID, _ := SplitKey(key)
		deduped := readings[:0]
		for _, r := range readings {
			dk := DedupKey(missionID, r.Sensor, r.TS)
			if seen.SeenRecently(dk) {
				continue
			}
			seen.Mark(dk)
			deduped = append(deduped, r)
		}
		if len(deduped) == 0 {
			continue
		}
		if err := store.CommitWindow(ctx, key, windowUnix, deduped); err != nil {
			log.Printf("flush error for key %s: %v", key, err)
		}
	}
}
