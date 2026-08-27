export type ProductKind =
  | 'mesh_glb' // O-1 glTF/GLB
  | 'mesh_3dtiles' // O-1 Cesium 3D Tiles tileset
  | 'point_cloud_laz' // O-2 classified LAS/LAZ
  | 'point_cloud_ply' // O-2 PLY variant
  | 'gaussian_splat' // survey-track 3DGS scene (architect/03 §6)
  | 'orthomosaic' // O-3 GeoTIFF/COG
  | 'dsm' // O-4
  | 'dtm' // O-4
  | 'trajectory' // O-5 COLMAP text + GeoJSON track
  | 'confidence_raster' // O-6
  | 'qa_report' // O-7
  | 'provenance'; // O-9

// architect/03 §8: fast-track products carry `quality: draft` end-to-end so
// they can never be confused with the survey-grade product (day-27 surfaces
// this distinction directly in the UI).
export type ProductQuality = 'draft' | 'survey';

export interface Product {
  id: string;
  missionId: string;
  kind: ProductKind;
  format: string; // 'glb' | 'laz' | 'ply' | 'geotiff' | 'geojson' | 'json' | ...
  url: string; // signed/proxied MinIO URL from the product catalog response
  crs: string; // e.g. 'EPSG:4978', 'EPSG:32633'
  bbox: number[]; // [minX,minY,minZ,maxX,maxY,maxZ] or 2D form
  checksum: string; // sha256, matches provenance manifest (O-9)
  quality: ProductQuality;
  provenanceRef: string | null;
  sizeBytes: number;
  // product-svc-computed summary stat for `confidence_raster` products only
  // (architect/02 §3); percent of the observable scene with valid,
  // non-occluded geometry. Absent for every other ProductKind.
  coveragePct?: number;
}
