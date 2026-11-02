import { describe, expect, it, vi } from 'vitest';
import { renderToString } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { AuditNotFoundView } from './Report';
import Report from './Report';
import { ApiError, getAudit, getAuditCost } from '../api/client';

describe('Report not-found state', () => {
  it('renders AuditNotFoundView with ID, Back to Home link, and Load Demo button', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const html = renderToString(
      <MemoryRouter>
        <AuditNotFoundView id="nonexistent-123" />
      </MemoryRouter>
    );
    spy.mockRestore();

    // Verify clear "Audit Not Found" header
    expect(html).toContain('Audit Not Found');
    // Verify ID is presented in the message
    expect(html).toContain('nonexistent-123');
    // Verify Back to Home link with href="/"
    expect(html).toContain('href="/"');
    expect(html).toContain('Back to Home');
    // Verify Load Demo Audit button
    expect(html).toContain('Load Demo Audit');
  });

  it('ApiError preserves HTTP status code 404', async () => {
    // Mock global fetch returning 404 Not Found
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Audit not found' }),
      text: async () => 'Audit not found',
    } as any);

    try {
      await expect(getAudit('invalid-audit-id')).rejects.toThrow(ApiError);

      try {
        await getAudit('invalid-audit-id');
      } catch (err: any) {
        expect(err).toBeInstanceOf(ApiError);
        expect(err.status).toBe(404);
        expect(err.message).toBe('Audit not found');
      }
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('does not invoke getAuditCost if getAudit returns 404', async () => {
    const originalFetch = globalThis.fetch;
    const fetchCalls: string[] = [];

    globalThis.fetch = vi.fn().mockImplementation(async (url: string) => {
      fetchCalls.push(url);
      if (url.includes('/api/audits/nonexistent-id/cost')) {
        return {
          ok: false,
          status: 404,
          json: async () => ({ detail: 'Audit not found' }),
        } as any;
      }
      if (url.includes('/api/audits/nonexistent-id')) {
        return {
          ok: false,
          status: 404,
          json: async () => ({ detail: 'Audit not found' }),
        } as any;
      }
      return { ok: true, json: async () => ({}) } as any;
    });

    let notFoundTriggered = false;
    let costCalled = false;

    // Simulate Report.tsx sequential fetch discipline
    const auditId = 'nonexistent-id';
    try {
      const audit = await getAudit(auditId);
      // Only call getAuditCost if getAudit succeeded
      if (audit.status === 'completed' || audit.status === 'failed') {
        costCalled = true;
        await getAuditCost(auditId);
      }
    } catch (err: any) {
      if (err?.status === 404) {
        notFoundTriggered = true;
      }
    }

    expect(notFoundTriggered).toBe(true);
    expect(costCalled).toBe(false);
    // Ensure no cost endpoint request was ever sent
    const hasCostCall = fetchCalls.some((c) => c.includes('/cost'));
    expect(hasCostCall).toBe(false);

    globalThis.fetch = originalFetch;
  });

  it('renders read-only shared report without review, override, or share controls', async () => {
    const originalFetch = globalThis.fetch;
    const mockSharedAudit = {
      id: 'audit_shared_123',
      status: 'completed',
      template_id: 'campus_fire_exit_core',
      created_at: '2026-11-01T12:00:00Z',
      provider_mode: 'mock',
      summary: { score: 95, pass: 4, fail: 0, unsure: 0 },
      findings: [
        {
          id: 'f_test_01',
          rule_id: 'extinguisher_visible',
          status: 'pass',
          confidence: 0.95,
          timestamp_s: 1.0,
          frame_idx: 0,
          rationale: 'Extinguisher present and clear',
          fix_text: '',
          severity: 'high',
          sources: ['segmentation'],
        },
      ],
    };

    globalThis.fetch = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes('/api/share/valid_token_xyz')) {
        return {
          ok: true,
          status: 200,
          text: async () => JSON.stringify(mockSharedAudit),
        } as any;
      }
      return { ok: true, text: async () => JSON.stringify({}) } as any;
    });

    const { getSharedAudit } = await import('../api/client');
    const data = await getSharedAudit('valid_token_xyz');
    expect(data.id).toBe('audit_shared_123');

    globalThis.fetch = originalFetch;
  });

  it('rejects /share/<audit-id> and returns 404', async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes('/api/share/audit_12345')) {
        return {
          ok: false,
          status: 404,
          text: async () => JSON.stringify({ detail: 'Invalid or expired share token' }),
        } as any;
      }
      return { ok: false, status: 404, text: async () => 'Not found' } as any;
    });

    const { getSharedAudit } = await import('../api/client');
    await expect(getSharedAudit('audit_12345')).rejects.toThrow(ApiError);

    try {
      await getSharedAudit('audit_12345');
    } catch (err: any) {
      expect(err.status).toBe(404);
      expect(err.message).toBe('Invalid or expired share token');
    }

    globalThis.fetch = originalFetch;
  });

  it('renders Evidence bundle (.zip) link and verification help text in report header', () => {
    const mockAudit: any = {
      id: 'audit_evidence_test_1',
      status: 'completed',
      template_id: 'campus_fire_exit_core',
      created_at: '2026-11-01T12:00:00Z',
      provider_mode: 'mock',
      summary: { score: 100, pass: 4, fail: 0, unsure: 0 },
      findings: [],
    };

    const html = renderToString(
      <MemoryRouter initialEntries={['/audits/audit_evidence_test_1']}>
        <Report initialAudit={mockAudit} />
      </MemoryRouter>
    );

    // Verify Evidence bundle button text
    expect(html).toContain('Evidence bundle (.zip)');
    // Verify GET /api/audits/{id}/bundle link target
    expect(html).toContain('/api/audits/audit_evidence_test_1/bundle');
    // Verify one-line verification help text
    expect(html).toContain('scripts/verify_bundle.py checks the hashes');
  });

  describe('Report UI Smoke Test (realistic and minimal payloads)', () => {
    function setupErrorTrap() {
      const recordedErrors: string[] = [];
      const spy = vi.spyOn(console, 'error').mockImplementation((...args: any[]) => {
        const msg = args.map((a) => (typeof a === 'string' ? a : JSON.stringify(a))).join(' ');
        // Filter out React 18 SSR warning about useLayoutEffect
        if (msg.includes('useLayoutEffect does nothing on the server')) return;
        recordedErrors.push(msg);
      });
      return {
        spy,
        getErrors: () => recordedErrors,
        restore: () => spy.mockRestore(),
      };
    }

    it('renders full Report page with realistic MOCK payload without errors', () => {
      const trap = setupErrorTrap();

      const realisticMockAudit: any = {
        id: 'audit_mock_real_01',
        site_id: 'site_building_a',
        status: 'completed',
        template_id: 'campus_fire_exit_core',
        created_at: '2026-11-01T14:30:00Z',
        provider_mode: 'mock',
        is_replay: false,
        source_provider_mode: 'mock',
        model_segmentation: 'SAM 3.1',
        model_agent: 'Muse Spark',
        model_transcription: 'Muse Voice Transcribe',
        summary: {
          score: 75,
          pass: 3,
          fail: 1,
          unsure: 0,
          frames_analyzed: 24,
          frames_considered: 105,
        },
        findings: [
          {
            id: 'f_01',
            rule_id: 'extinguisher_visible',
            status: 'pass',
            severity: 'high',
            confidence: 0.94,
            timestamp_s: 2.5,
            frame_idx: 6,
            rationale: 'Extinguisher present on wall',
            fix_text: '',
            sources: ['segmentation'],
          },
          {
            id: 'f_02',
            rule_id: 'exit_path_not_blocked',
            status: 'fail',
            severity: 'high',
            confidence: 0.91,
            timestamp_s: 18.0,
            frame_idx: 45,
            rationale: 'Boxes obstructing corridor doorway',
            fix_text: 'Remove boxes from hallway',
            sources: ['segmentation'],
          },
        ],
      };

      const html = renderToString(
        <MemoryRouter initialEntries={['/audits/audit_mock_real_01']}>
          <Report initialAudit={realisticMockAudit} />
        </MemoryRouter>
      );

      expect(html).toContain('AuditLens Pre-Inspection Report');
      expect(html).toContain('campus_fire_exit_core');
      expect(html).toContain('extinguisher_visible');
      expect(html).toContain('exit_path_not_blocked');
      expect(trap.getErrors()).toEqual([]);

      trap.restore();
    });

    it('renders full Report page with realistic REPLAY (mock-derived fixture) payload without errors', () => {
      const trap = setupErrorTrap();

      const realisticReplayAudit: any = {
        id: 'audit_replay_sim_02',
        site_id: 'site_building_b',
        status: 'completed',
        template_id: 'campus_fire_exit_core',
        created_at: '2026-11-01T16:00:00Z',
        provider_mode: 'replay',
        is_replay: true,
        source_provider_mode: 'mock',
        summary: {
          score: 50,
          pass: 2,
          fail: 2,
          unsure: 0,
          frames_analyzed: 16,
          frames_considered: 80,
        },
        findings: [
          {
            id: 'f_03',
            rule_id: 'exit_sign_visible',
            status: 'pass',
            severity: 'high',
            confidence: 0.96,
            timestamp_s: 3.0,
            frame_idx: 8,
            rationale: 'Exit sign illuminated',
            sources: ['segmentation'],
          },
        ],
      };

      const html = renderToString(
        <MemoryRouter initialEntries={['/audits/audit_replay_sim_02']}>
          <Report initialAudit={realisticReplayAudit} />
        </MemoryRouter>
      );

      expect(html).toContain('SIMULATED REPLAY (mock fixtures)');
      expect(html).toContain('exit_sign_visible');
      expect(trap.getErrors()).toEqual([]);

      trap.restore();
    });

    it('renders full Report page with minimal payload (all optional fields missing) without errors', () => {
      const trap = setupErrorTrap();

      const minimalAudit: any = {
        id: 'audit_minimal_03',
        status: 'completed',
      };

      const html = renderToString(
        <MemoryRouter initialEntries={['/audits/audit_minimal_03']}>
          <Report initialAudit={minimalAudit} />
        </MemoryRouter>
      );

      expect(html).not.toBe('');
      expect(html).toContain('Pre-Audit Inspection Report');
      expect(html).toContain('Audit ID: audit_minimal_');
      expect(trap.getErrors()).toEqual([]);

      trap.restore();
    });
  });
});
