package db

import (
	"testing"
)

func TestValidatePolygonGeoJSON(t *testing.T) {
	validPolygon := `{"type":"Polygon","coordinates":[[[0,0],[0,1],[1,1],[1,0],[0,0]]]}`
	if err := ValidatePolygonGeoJSON(validPolygon); err != nil {
		t.Errorf("expected valid polygon, got error: %v", err)
	}

	invalidType := `{"type":"Point","coordinates":[0,0]}`
	if err := ValidatePolygonGeoJSON(invalidType); err == nil {
		t.Errorf("expected error for non-Polygon type, got nil")
	}

	unclosedRing := `{"type":"Polygon","coordinates":[[[0,0],[0,1],[1,1],[1,0],[0,2]]]}`
	if err := ValidatePolygonGeoJSON(unclosedRing); err == nil {
		t.Errorf("expected error for unclosed ring, got nil")
	}

	tooShortRing := `{"type":"Polygon","coordinates":[[[0,0],[0,1],[0,0]]]}`
	if err := ValidatePolygonGeoJSON(tooShortRing); err == nil {
		t.Errorf("expected error for ring with < 4 coordinates, got nil")
	}

	malformedJSON := `{invalid}`
	if err := ValidatePolygonGeoJSON(malformedJSON); err == nil {
		t.Errorf("expected error for malformed JSON, got nil")
	}
}
