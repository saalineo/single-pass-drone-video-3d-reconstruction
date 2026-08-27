import { apiClient } from './client';
import type { Mission, CreateMissionRequest } from '@/types/mission';
import type { Product } from '@/types/product';

export const missionApi = {
  list: () => apiClient.get<Mission[]>('/missions'),
  get: (id: string) => apiClient.get<Mission>(`/missions/${id}`),
  create: (req: CreateMissionRequest) =>
    apiClient.post<{ mission_id: string }>('/missions', req),
  getProducts: (id: string) => apiClient.get<Product[]>(`/missions/${id}/products`),
  requestRoi: (id: string, polygonAoi: GeoJSON.Polygon, qualityPreset: string) =>
    apiClient.post<{ workflow_id: string }>(`/missions/${id}/roi`, {
      polygon_aoi: polygonAoi,
      quality_preset: qualityPreset,
    }),
};
