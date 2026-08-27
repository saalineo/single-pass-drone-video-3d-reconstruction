import type { StageState, MissionOverallStatus } from '@/types/mission';

export interface PoseTrailFeature {
  type: 'Feature';
  geometry: { type: 'Point'; coordinates: [lon: number, lat: number, alt: number] };
  properties: {
    timestamp: string; // ISO 8601
    headingDeg: number;
    quality: 'draft'; // architect/03 §8: fast-track products always carry this
  };
}

export interface TileUpdate {
  tileUrl: string;
  bbox: [minLon: number, minLat: number, maxLon: number, maxLat: number];
  zoom: number;
}

export interface CoverageAlert {
  id: string;
  severity: 'info' | 'warning' | 'critical';
  message: string; // e.g. "Missed coverage: eastern facade"
  aoi: GeoJSON.Polygon | null;
  timestamp: string;
}

export interface LinkHealth {
  rssiDbm: number;
  linkState: 'nominal' | 'degraded' | 'lost';
  bitrateKbps: number;
}

export interface MissionStatusPayload {
  missionId: string;
  overallStatus: MissionOverallStatus;
  stages: StageState[];
  accuracyWarning: string | null; // architect/02 §7: pose divergence flagged, never silent
  updatedAt: string;
}

export type LiveFeedMessage =
  | { type: 'pose'; payload: PoseTrailFeature }
  | { type: 'tile'; payload: TileUpdate }
  | { type: 'alert'; payload: CoverageAlert }
  | { type: 'link_health'; payload: LinkHealth }
  | { type: 'status'; payload: MissionStatusPayload };
