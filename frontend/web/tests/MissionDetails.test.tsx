import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { vi } from 'vitest';
import { server } from './setupTests';
import type { Mission, StageState } from '@/types/mission';

// MapViewer mounts a real Cesium <Viewer>, which needs a WebGL context jsdom
// doesn't provide (same GPU-rendering constraint day-25 calls out for
// Viewer3D). Stub both heavy viewers so this test stays focused on the
// page-level status-ladder wiring; the actual renders are manual/visual QA.
vi.mock('@/components/MapViewer', () => ({ MapViewer: () => null }));
vi.mock('@/components/Viewer3D', () => ({ Viewer3D: () => null }));
// Avoid opening a real WebSocket against a mission-svc that doesn't exist in
// this test run; useMissionStatus's live-status wiring is exercised by
// reading `status`/`connState`, not by a real socket round-trip here.
vi.mock('@/api/liveFeed', () => ({ connectLiveFeed: () => () => {} }));

const { default: MissionDetails } = await import('@/pages/MissionDetails');

const ALL_STAGES: StageState['stage'][] = [
  'ingest',
  'pose_estimation',
  'dynamic_masking',
  'depth_fusion',
  'meshing',
  'georeferencing',
  'publishing',
];

function stages(state: StageState['state']): StageState[] {
  return ALL_STAGES.map((stage) => ({ stage, state, progressPct: 100, etaSeconds: null }));
}

function baseMission(overrides: Partial<Mission>): Mission {
  return {
    id: 'mission-x',
    name: 'survey-alpha',
    status: 'processing',
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
    ...overrides,
  };
}

function renderDetails(mission: Mission) {
  const apiBase = import.meta.env.VITE_API_BASE_URL ?? '/v1';
  server.use(
    http.get(`${apiBase}/missions/:id`, () => HttpResponse.json(mission)),
    http.get(`${apiBase}/missions/:id/products`, () => HttpResponse.json([])),
  );
  const qc = new QueryClient();
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/missions/${mission.id}`]}>
        <Routes>
          <Route path="/missions/:missionId" element={<MissionDetails />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('shows the stage ladder for an in-progress mission', async () => {
  renderDetails(baseMission({ status: 'processing', stages: stages('running') }));
  expect(await screen.findByText('Ingest & Curation')).toBeInTheDocument();
  for (const label of [
    'Pose Estimation',
    'Dynamic Masking',
    'Depth Fusion',
    'Meshing',
    'Georeferencing',
    'Publishing',
  ]) {
    expect(screen.getByText(label)).toBeInTheDocument();
  }
});

test('hides the stage ladder once a mission is complete', async () => {
  renderDetails(baseMission({ status: 'complete', stages: stages('complete') }));
  await screen.findByText('survey-alpha');
  expect(screen.queryByText('Ingest & Curation')).not.toBeInTheDocument();
});
