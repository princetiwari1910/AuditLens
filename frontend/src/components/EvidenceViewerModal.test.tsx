import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import EvidenceViewerModal from './EvidenceViewerModal';
import type { Finding } from '../api/types';

describe('EvidenceViewerModal component', () => {
  const sampleFinding: Finding = {
    id: 'f_test_01',
    rule_id: 'extinguisher_visible',
    status: 'pass',
    confidence: 0.94,
    timestamp_s: 3.5,
    frame_idx: 2,
    overlay_url: '/api/audits/123/overlays/f_test_01',
    rationale: 'Fire extinguisher identified mounted on wall at 3.5s.',
    fix_text: 'Keep clear area unobstructed.',
    severity: 'high',
    sources: ['segmentation'],
    support_count: 3,
    stability: 0.95,
    decision_policy: 'mask_backed_pass',
    strongest_evidence: {
      id: 'ev_01',
      frame_id: 2,
      ts: 3.5,
      source: 'sam',
      concept: 'fire extinguisher',
      score: 0.94,
      strength: 'mask_backed',
    },
    evidence_ledger: [
      {
        id: 'ev_01',
        frame_id: 2,
        ts: 3.5,
        source: 'sam',
        concept: 'fire extinguisher',
        score: 0.94,
        strength: 'mask_backed',
      },
      {
        id: 'ev_02',
        frame_id: 3,
        ts: 4.5,
        source: 'sam',
        concept: 'fire extinguisher',
        score: 0.88,
        strength: 'mask_backed',
      },
    ],
    escalation_steps: [
      {
        step: 1,
        action: '2x2 zoom tiles',
        outcome: 'Found match with 94% score',
      },
    ],
  };

  it('renders nothing when isOpen is false', () => {
    const html = renderToString(
      <EvidenceViewerModal
        finding={sampleFinding}
        isOpen={false}
        onClose={() => {}}
      />
    );
    expect(html).toBe('');
  });

  it('renders evidence details, strength badge, cited frames, and keyboard legend when isOpen is true', () => {
    const html = renderToString(
      <EvidenceViewerModal
        finding={sampleFinding}
        isOpen={true}
        onClose={() => {}}
      />
    );

    // Rule & Status
    expect(html).toContain('extinguisher_visible');
    expect(html).toContain('confidence');
    expect(html).toContain('94');

    // Strength Badge
    expect(html).toContain('Mask-Backed Visual Evidence');

    // Reasoning
    expect(html).toContain('Fire extinguisher identified mounted on wall at 3.5s.');

    // Cited Frames
    expect(html).toContain('Cited Keyframes');
    expect(html).toContain('fire extinguisher');

    // Escalation Trace
    expect(html).toContain('Active Evidence Gathering');
    expect(html).toContain('2x2 zoom tiles');

    // Keyboard Shortcuts Legend
    expect(html).toContain('j / k');
    expect(html).toContain('Enter');
    expect(html).toContain('Esc');
  });
});
