import { describe, expect, it, vi, afterEach } from 'vitest';
import { ApiError, getHealth, createDemoAudit, getTemplates, getAudits } from './client';

describe('API client body stream handling', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('parses a successful JSON response cleanly without reading stream twice', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ status: 'ok', provider_mode: 'mock' }),
    } as any);

    const health = await getHealth();
    expect(health.status).toBe('ok');
    expect(health.provider_mode).toBe('mock');
  });

  it('handles error response with JSON detail without throwing body stream already read', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      text: async () => JSON.stringify({ detail: 'Invalid template specified' }),
    } as any);

    try {
      await createDemoAudit('invalid_template');
      expect.fail('Should have thrown ApiError');
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(400);
      expect(err.message).toBe('Invalid template specified');
      expect(err.message).not.toContain('body stream already read');
    }
  });

  it('handles error response with non-JSON plain text body without throwing body stream already read', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      text: async () => 'Bad Gateway: Upstream connection failed',
    } as any);

    try {
      await getHealth();
      expect.fail('Should have thrown ApiError');
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(502);
      expect(err.message).toBe('Bad Gateway: Upstream connection failed');
      expect(err.message).not.toContain('body stream already read');
    }
  });

  it('handles 204 or empty response body safely', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      text: async () => '',
    } as any);

    const res = await getHealth();
    expect(res).toEqual({});
  });

  it('rejects HTML body returned with 200 OK from SPA rewrite and falls back gracefully', async () => {
    const htmlBody = '<!doctype html><html><head><title>AuditLens</title></head><body><div id="root"></div></body></html>';
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => 'text/html; charset=utf-8' },
      text: async () => htmlBody,
    } as any);

    // getHealth should throw ApiError when receiving HTML
    await expect(getHealth()).rejects.toThrow(/Expected JSON/);

    // getTemplates falls back to bundled default templates
    const templates = await getTemplates();
    expect(Array.isArray(templates)).toBe(true);
    expect(templates.length).toBeGreaterThan(0);
    expect(templates[0].id).toBe('campus_fire_exit_core');

    // getAudits returns empty array instead of crashing
    const audits = await getAudits();
    expect(audits).toEqual([]);
  });
});
