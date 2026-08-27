import { render, screen } from '@testing-library/react';
import { CoverageGapBadge } from '@/components/CoverageGapBadge';

test('flips to the red gap styling below the 90% NFR-5 threshold', () => {
  render(<CoverageGapBadge coveragePct={82} />);
  expect(screen.getByText(/Coverage gap: 82% observed/)).toHaveClass('bg-red-100');
});

test('uses neutral styling at or above the 90% threshold', () => {
  render(<CoverageGapBadge coveragePct={95} />);
  expect(screen.getByText(/95% coverage/)).toHaveClass('bg-slate-100');
});
