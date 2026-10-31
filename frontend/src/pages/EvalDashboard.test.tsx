import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { renderToString } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import EvalDashboard from './EvalDashboard';
import * as client from '../api/client';

describe('EvalDashboard component', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('renders loading state initially during SSR/renderToString', () => {
    const html = renderToString(
      <MemoryRouter>
        <EvalDashboard />
      </MemoryRouter>
    );

    expect(html).toContain('Loading evaluation benchmark &amp; calibration data');
  });

  it('verifies client getLatestEval returns structured metrics', async () => {
    const mockPayload: client.EvalLatestResponse = {
      timestamp: '2026-10-31T10:00:00Z',
      provider_mode: 'mock',
      allow_mock: true,
      simulated: true,
      benchmark_details: [],
      pipeline_summary: {
        mode: 'pipeline',
        total_clips: 1,
        total_evaluations: 10,
        correct_count: 9,
        unsure_count: 1,
        overall_accuracy: 0.9,
        unsure_rate: 0.1,
        macro_f1: 0.88,
        macro_precision: 0.85,
        macro_recall: 0.92,
        average_latency_s: 1.2,
        average_cost_usd: 0.005,
        rule_metrics: {},
        reliability_curve: [
          { bin: '0.80-0.90', count: 5, confidence: 0.85, accuracy: 0.9 },
        ],
        accuracy_vs_abstain: [
          { threshold: 0.7, abstain_rate: 0.1, accuracy: 0.95, decided_count: 9 },
        ],
        failure_cases: [],
      },
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockPayload,
    } as any);

    const result = await client.getLatestEval();
    expect(result.provider_mode).toBe('mock');
    expect(result.pipeline_summary.overall_accuracy).toBe(0.9);
    expect(result.pipeline_summary.unsure_rate).toBe(0.1);
    expect(result.pipeline_summary.reliability_curve.length).toBe(1);
  });
});
