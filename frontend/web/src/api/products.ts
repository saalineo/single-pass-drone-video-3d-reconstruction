import { missionApi } from './missions';

// Product reads are all scoped under a mission today (GET /v1/missions/{id}/products);
// re-exported here as the dedicated product-API seam so a future
// product-svc-direct endpoint (e.g. signed-URL refresh, see
// hooks/useSignedProductUrl.ts) doesn't have to be threaded through missionApi.
export const productApi = {
  listForMission: missionApi.getProducts,
};
