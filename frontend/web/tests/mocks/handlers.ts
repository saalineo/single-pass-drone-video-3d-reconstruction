import { http, HttpResponse } from 'msw';
import type { Mission } from '@/types/mission';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/v1';

const fixtureMissions: Mission[] = [
  {
    id: 'mission-1',
    name: 'survey-alpha',
    status: 'complete',
    createdAt: '2026-08-01T12:00:00Z',
    areaOfInterest: {
      type: 'Polygon',
      coordinates: [
        [
          [-122.42, 37.77],
          [-122.41, 37.77],
          [-122.41, 37.78],
          [-122.42, 37.78],
          [-122.42, 37.77],
        ],
      ],
    },
    classification: 'unclassified',
    expectedSensors: ['rgb'],
    areaSqKm: 1.24,
    stages: [],
  },
];

export const handlers = [
  http.get(`${API_BASE}/missions`, () => HttpResponse.json(fixtureMissions)),
  http.get(`${API_BASE}/missions/:id`, ({ params }) => {
    const mission = fixtureMissions.find((m) => m.id === params.id);
    return mission ? HttpResponse.json(mission) : new HttpResponse(null, { status: 404 });
  }),
  http.get(`${API_BASE}/missions/:id/products`, () => HttpResponse.json([])),
];
