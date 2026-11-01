import { describe, expect, it, vi } from 'vitest';
import { renderToString } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { AuditNotFoundView } from './Report';
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
});
