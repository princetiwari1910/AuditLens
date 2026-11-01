import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import ReviewQueuePanel from './ReviewQueuePanel';
import type { Finding } from '../api/types';
import type { AuditLogEntry } from '../api/client';

describe('ReviewQueuePanel component', () => {
  const sampleFinding: Finding = {
    id: 'f_rev_01',
    rule_id: 'exit_path_not_blocked',
    status: 'unsure',
    ai_verdict: 'unsure',
    final_verdict: 'unsure',
    confidence: 0.65,
    timestamp_s: 12.0,
    frame_idx: 6,
    overlay_url: '/api/audits/123/overlays/f_rev_01',
    rationale: 'Potential box obstruction detected near hallway doorway.',
    fix_text: 'Remove obstruction from egress route.',
    severity: 'high',
    sources: ['segmentation'],
  };

  const sampleLogs: AuditLogEntry[] = [
    {
      id: 'log_1',
      audit_id: 'audit_test_123',
      finding_id: 'f_rev_01',
      actor_label: 'Lead Inspector John',
      action: 'override_fail',
      before: 'unsure',
      after: 'fail',
      note: 'Confirmed hallway is partially blocked by delivery cart.',
      ts: '2026-11-01T12:00:00Z',
    },
  ];

  it('renders side-by-side AI and final verdicts', () => {
    const html = renderToString(
      <ReviewQueuePanel
        auditId="audit_test_123"
        finding={sampleFinding}
        auditLogs={sampleLogs}
        onReviewSuccess={() => {}}
      />
    );

    expect(html).toContain('Human Review Queue');
    expect(html).toContain('exit_path_not_blocked');
    expect(html).toContain('AI:');
    expect(html).toContain('Final:');
    expect(html).toContain('Review');
  });

  it('renders review action buttons', () => {
    const html = renderToString(
      <ReviewQueuePanel
        auditId="audit_test_123"
        finding={sampleFinding}
        auditLogs={[]}
        onReviewSuccess={() => {}}
      />
    );

    expect(html).toContain('Approve AI Verdict');
    expect(html).toContain('Override → Pass');
    expect(html).toContain('Override → Fail');
    expect(html).toContain('Commit Review Decision');
  });

  it('renders audit history entries if present', () => {
    const html = renderToString(
      <ReviewQueuePanel
        auditId="audit_test_123"
        finding={sampleFinding}
        auditLogs={sampleLogs}
        onReviewSuccess={() => {}}
      />
    );

    expect(html).toContain('Finding Audit History');
    expect(html).toContain('Lead Inspector John');
    expect(html).toContain('override_fail');
    expect(html).toContain('Confirmed hallway is partially blocked by delivery cart.');
    expect(html).toContain('Verdict Transition');
  });
});
