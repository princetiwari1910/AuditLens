import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import TracePage from './TracePage';

describe('TracePage component', () => {
  it('renders loading state initially during SSR/renderToString', () => {
    const html = renderToString(
      <MemoryRouter>
        <TracePage />
      </MemoryRouter>
    );

    expect(html).toContain('Loading execution trace');
  });

  it('renders aligned frame counts matching report header (N of M frames analyzed)', () => {
    const mockTrace: any = {
      audit_id: 'audit_trace_test_01',
      totals: {
        total_spans: 4,
        total_latency_ms: 150,
        total_cost_usd: 0.0035,
        budget_cap_usd: 1.0,
        cache_hits: 1,
        cache_hit_rate: 0.25,
        calls_saved_by_cache: 1,
        frames_considered: 25,
        frames_analyzed: 12,
        frames_saved_by_selection: 13,
        calls_saved_by_keyframes: 13,
      },
      spans: [
        {
          id: 1,
          stage: 'segmentation',
          model: 'sam-3.1',
          concept: 'fire extinguisher',
          latency_ms: 50,
          cost_usd: 0.001,
          cache_hit: false,
          retries: 0,
          step_reason: 'Primary visual detector pass',
          simulated: true,
          created_at: '2026-11-01T12:00:00Z',
        },
      ],
    };

    const html = renderToString(
      <MemoryRouter>
        <TracePage initialTrace={mockTrace} />
      </MemoryRouter>
    );

    expect(html).toContain('12 of 25');
    expect(html).toContain('12 of 25 frames analyzed');
    // Verify configured budget cap of $1.00 (not hardcoded $0.05)
    expect(html).toContain('1.00');
    expect(html).toContain('guard');
    // Verify SIMULATED span badge
    expect(html).toContain('SIMULATED');
  });
});
