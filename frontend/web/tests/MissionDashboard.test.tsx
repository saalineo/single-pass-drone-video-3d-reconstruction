import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import MissionDashboard from '@/pages/MissionDashboard';

test('renders mission rows from the API', async () => {
  const qc = new QueryClient();
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MissionDashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  // Both the md+ table and the small-screen card list render unconditionally
  // (visibility switches on a CSS media query, not a DOM branch), so the
  // fixture mission's name legitimately appears twice.
  expect(await screen.findAllByText(/survey-alpha/i)).toHaveLength(2);
});
