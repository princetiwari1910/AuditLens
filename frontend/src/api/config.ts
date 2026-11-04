/** Application-wide API configuration. */

export const DEFAULT_PROD_API_URL = 'https://auditlens-p9fm.onrender.com';

/**
 * Normalizes an API base URL by stripping trailing slashes and any trailing /api segment.
 */
export function normalizeApiBaseUrl(rawUrl: string | undefined): string {
  if (!rawUrl || typeof rawUrl !== 'string') return '';
  let cleaned = rawUrl.trim().replace(/\/+$/, '');
  if (cleaned.endsWith('/api')) {
    cleaned = cleaned.slice(0, -4).replace(/\/+$/, '');
  }
  return cleaned;
}

const envUrl = normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL as string | undefined);

export const API_BASE_URL: string = (() => {
  // 1. Explicitly configured VITE_API_BASE_URL takes highest priority
  if (envUrl) {
    return envUrl;
  }
  // 2. In local dev (npm run dev) or unit tests, use empty string to leverage Vite dev proxy (/api -> http://127.0.0.1:8000)
  if (import.meta.env.DEV || import.meta.env.MODE === 'test') {
    return '';
  }
  // 3. In production builds (Vercel deployment), target the deployed Render backend
  return DEFAULT_PROD_API_URL;
})();

/**
 * Builds a normalized, fully qualified or relative API path.
 * Guarantees no duplicate /api/api/ segments regardless of input formatting.
 */
export function buildApiUrl(path: string): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  if (cleanPath.startsWith('/api/')) {
    return `${API_BASE_URL}${cleanPath}`;
  }
  return `${API_BASE_URL}/api${cleanPath}`;
}

