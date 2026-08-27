import { render, screen } from '@testing-library/react';
import { QualityBadge } from '@/components/QualityBadge';

test('renders the amber DRAFT variant for a draft-quality product', () => {
  render(<QualityBadge quality="draft" />);
  expect(screen.getByText(/DRAFT/)).toHaveClass('bg-amber-100');
});

test('renders the emerald SURVEY variant for a survey-quality product', () => {
  render(<QualityBadge quality="survey" />);
  expect(screen.getByText(/SURVEY/)).toHaveClass('bg-emerald-100');
});
