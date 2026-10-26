/**
 * UI formatting and status helpers with accessibility & color-blind friendliness.
 */

export type FindingStatus = 'pass' | 'fail' | 'unsure';
export type SeverityLevel = 'high' | 'medium' | 'low';

export interface StatusMeta {
  label: string;
  badgeClass: string;
  textClass: string;
  borderClass: string;
  colorHex: string;
}

export function formatTimestamp(seconds: number): string {
  if (isNaN(seconds) || seconds < 0) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export function getStatusMeta(status: string): StatusMeta {
  const norm = status.toLowerCase();
  switch (norm) {
    case 'pass':
      return {
        label: 'PASS',
        badgeClass: 'bg-green-100 text-green-900 border-green-300 dark:bg-green-950 dark:text-green-200 dark:border-green-800',
        textClass: 'text-green-700 dark:text-green-400',
        borderClass: 'border-green-500',
        colorHex: '#16a34a',
      };
    case 'fail':
      return {
        label: 'FAIL',
        badgeClass: 'bg-red-100 text-red-900 border-red-300 dark:bg-red-950 dark:text-red-200 dark:border-red-800',
        textClass: 'text-red-700 dark:text-red-400',
        borderClass: 'border-red-500',
        colorHex: '#dc2626',
      };
    case 'unsure':
    default:
      return {
        label: 'NEEDS REVIEW',
        badgeClass: 'bg-amber-100 text-amber-900 border-amber-300 dark:bg-amber-950 dark:text-amber-200 dark:border-amber-800',
        textClass: 'text-amber-700 dark:text-amber-400',
        borderClass: 'border-amber-500',
        colorHex: '#d97706',
      };
  }
}

export function getSeverityMeta(severity: string) {
  const norm = severity.toLowerCase();
  switch (norm) {
    case 'high':
      return { label: 'High Severity', badge: 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300' };
    case 'medium':
      return { label: 'Medium Severity', badge: 'bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300' };
    case 'low':
    default:
      return { label: 'Low Severity', badge: 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300' };
  }
}

export function getScoreGrade(score: number): { label: string; colorClass: string } {
  if (score >= 80) return { label: 'Good Compliance', colorClass: 'text-green-600 dark:text-green-400' };
  if (score >= 50) return { label: 'Action Required', colorClass: 'text-amber-600 dark:text-amber-400' };
  return { label: 'High Risk', colorClass: 'text-red-600 dark:text-red-400' };
}
