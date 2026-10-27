/** Application-wide API configuration. */

export const API_BASE_URL: string = (
  (import.meta.env.VITE_API_BASE_URL as string | undefined) || ''
).replace(/\/$/, '');
