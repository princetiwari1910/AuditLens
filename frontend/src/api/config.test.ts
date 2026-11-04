import { describe, expect, it } from 'vitest';
import { normalizeApiBaseUrl, buildApiUrl, DEFAULT_PROD_API_URL, API_BASE_URL } from './config';

describe('API Configuration & URL Normalization', () => {
  it('defines correct production fallback URL', () => {
    expect(DEFAULT_PROD_API_URL).toBe('https://auditlens-p9fm.onrender.com');
    expect(typeof API_BASE_URL).toBe('string');
  });

  it('normalizes various input formats correctly', () => {
    expect(normalizeApiBaseUrl('')).toBe('');
    expect(normalizeApiBaseUrl('   ')).toBe('');
    expect(normalizeApiBaseUrl('https://auditlens-p9fm.onrender.com')).toBe('https://auditlens-p9fm.onrender.com');
    expect(normalizeApiBaseUrl('https://auditlens-p9fm.onrender.com/')).toBe('https://auditlens-p9fm.onrender.com');
    expect(normalizeApiBaseUrl('https://auditlens-p9fm.onrender.com/api')).toBe('https://auditlens-p9fm.onrender.com');
    expect(normalizeApiBaseUrl('https://auditlens-p9fm.onrender.com/api/')).toBe('https://auditlens-p9fm.onrender.com');
    expect(normalizeApiBaseUrl('http://127.0.0.1:8000/api')).toBe('http://127.0.0.1:8000');
  });

  it('buildApiUrl avoids duplicate /api/api/ segments', () => {
    // Relative paths without /api
    const url1 = buildApiUrl('/health');
    expect(url1).not.toContain('/api/api');
    expect(url1).toMatch(/\/api\/health$/);

    // Paths that already contain /api/
    const url2 = buildApiUrl('/api/audits/123/overlays/456');
    expect(url2).not.toContain('/api/api');
    expect(url2).toMatch(/\/api\/audits\/123\/overlays\/456$/);

    // Paths without leading slash
    const url3 = buildApiUrl('templates/campus_fire_exit_core');
    expect(url3).not.toContain('/api/api');
    expect(url3).toMatch(/\/api\/templates\/campus_fire_exit_core$/);
  });
});
