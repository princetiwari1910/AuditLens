import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import ModelsUsedPanel from './ModelsUsedPanel';
import type { CostSummary } from '../api/client';

describe('ModelsUsedPanel component', () => {
  it('renders all three foundation models with roles, latencies, and costs', () => {
    const mockCost: CostSummary = {
      audit_id: 'test_audit_123',
      provider_mode: 'mock',
      total_calls: 8,
      total_cost_usd: 0.0245,
      by_provider: {
        segmentation: {
          name: 'Segmentation',
          model_id: 'SAM 3.1',
          role: 'SAM 3.1: finds and measures items',
          calls: 5,
          cache_hits: 2,
          latency_ms: 240,
          units: 5,
          cost_usd: 0.0100,
          simulated: true,
        },
        agent: {
          name: 'Agent / Reasoning',
          model_id: 'Muse Spark',
          role: 'Muse Spark: reasons over rules, dispatches tools, and evaluates evidence',
          calls: 2,
          cache_hits: 0,
          latency_ms: 60,
          units: 1.5,
          cost_usd: 0.0115,
          simulated: true,
        },
        transcription: {
          name: 'Voice Transcription',
          model_id: 'Muse Voice Transcribe',
          role: 'Muse Voice Transcribe: transcribes audio notes into searchable evidence',
          calls: 1,
          cache_hits: 0,
          latency_ms: 30,
          units: 0.5,
          cost_usd: 0.0030,
          simulated: true,
        },
      },
    };

    const html = renderToString(
      <ModelsUsedPanel
        costSummary={mockCost}
        providerMode="mock"
        models={{
          segmentation: 'SAM 3.1',
          agent: 'Muse Spark',
          transcription: 'Muse Voice Transcribe',
        }}
        isReplay={false}
      />
    );

    // Verify Models Used heading
    expect(html).toContain('Models Used &amp; Provider Evidence');
    // Verify all 3 model IDs
    expect(html).toContain('SAM 3.1');
    expect(html).toContain('Muse Spark');
    expect(html).toContain('Muse Voice Transcribe');
    // Verify roles
    expect(html).toContain('finds and measures items');
    expect(html).toContain('reasons over rules');
    expect(html).toContain('transcribes audio notes');
    // Verify latency and costs
    expect(html).toContain('240');
    expect(html).toContain('0.0100');
    // Verify Mock mode banner
    expect(html).toContain('Mock Mode: Simulated Detections');
  });

  it('renders Simulated Replay badge when isReplay is true and sourceProviderMode is mock', () => {
    const html = renderToString(
      <ModelsUsedPanel
        costSummary={null}
        providerMode="mock"
        isReplay={true}
        sourceProviderMode="mock"
      />
    );

    expect(html).toContain('SIMULATED REPLAY (mock fixtures)');
    expect(html).toContain('Latencies and costs are simulated.');
  });

  it('renders Recorded Run badge when isReplay is true and sourceProviderMode is record', () => {
    const html = renderToString(
      <ModelsUsedPanel
        costSummary={null}
        providerMode="replay"
        isReplay={true}
        sourceProviderMode="record"
      />
    );

    expect(html).toContain('RECORDED RUN (live providers)');
    expect(html).toContain('Latencies and costs are simulated.');
  });
});
