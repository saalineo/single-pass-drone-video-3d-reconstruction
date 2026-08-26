package db

import (
	"encoding/json"
	"fmt"
)

type geoJSONPolygon struct {
	Type        string         `json:"type"`
	Coordinates [][][2]float64 `json:"coordinates"`
}

func ValidatePolygonGeoJSON(raw string) error {
	var p geoJSONPolygon
	if err := json.Unmarshal([]byte(raw), &p); err != nil {
		return fmt.Errorf("invalid geojson: %w", err)
	}
	if p.Type != "Polygon" {
		return fmt.Errorf("expected Polygon, got %q", p.Type)
	}
	if len(p.Coordinates) == 0 || len(p.Coordinates[0]) < 4 {
		return fmt.Errorf("polygon ring must have >= 4 positions (closed ring)")
	}
	ring := p.Coordinates[0]
	if ring[0] != ring[len(ring)-1] {
		return fmt.Errorf("polygon ring must be closed (first == last position)")
	}
	return nil
}
