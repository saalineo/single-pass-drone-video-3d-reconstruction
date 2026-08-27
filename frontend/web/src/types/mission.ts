export type MissionStage =
  | 'ingest'
  | 'pose_estimation'
  | 'dynamic_masking'
  | 'depth_fusion'
  | 'meshing'
  | 'georeferencing'
  | 'publishing';

export interface StageState {
  stage: MissionStage;
  state: 'pending' | 'running' | 'complete' | 'failed';
  progressPct: number; // 0-100
  etaSeconds: number | null;
}

// Coarse status shown as a dashboard badge; StageState[] gives the detail
// ladder consumed by day-27's live status view.
export type MissionOverallStatus =
  | 'queued'
  | 'in_flight'
  | 'processing'
  | 'complete'
  | 'failed';

export interface Mission {
  id: string;
  name: string;
  status: MissionOverallStatus;
  createdAt: string; // ISO 8601 UTC
  areaOfInterest: GeoJSON.Polygon; // matches POST /v1/missions request body shape
  classification: string;
  expectedSensors: string[];
  areaSqKm: number;
  stages: StageState[];
}

export interface CreateMissionRequest {
  name: string;
  area_of_interest: GeoJSON.Polygon;
  classification: string;
  expected_sensors: string[];
}
