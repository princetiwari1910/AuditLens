import React from 'react';
import { Eye, ShieldAlert, Hash, Ruler, Users } from 'lucide-react';
import type { RuleType } from '../api/types';

interface RuleChipProps {
  type: RuleType;
  showIcon?: boolean;
}

export default function RuleChip({ type, showIcon = true }: RuleChipProps) {
  switch (type) {
    case 'presence':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-md bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 ring-1 ring-blue-700/10 dark:bg-blue-950/60 dark:text-blue-300 dark:ring-blue-400/20">
          {showIcon && <Eye className="h-3.5 w-3.5" />}
          Presence
        </span>
      );
    case 'absence':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-md bg-purple-50 px-2.5 py-1 text-xs font-medium text-purple-700 ring-1 ring-purple-700/10 dark:bg-purple-950/60 dark:text-purple-300 dark:ring-purple-400/20">
          {showIcon && <ShieldAlert className="h-3.5 w-3.5" />}
          Absence
        </span>
      );
    case 'count':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-md bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 ring-1 ring-indigo-700/10 dark:bg-indigo-950/60 dark:text-indigo-300 dark:ring-indigo-400/20">
          {showIcon && <Hash className="h-3.5 w-3.5" />}
          Count
        </span>
      );
    case 'measurement':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-md bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 ring-1 ring-emerald-700/10 dark:bg-emerald-950/60 dark:text-emerald-300 dark:ring-emerald-400/20">
          {showIcon && <Ruler className="h-3.5 w-3.5" />}
          Measurement
        </span>
      );
    case 'colocation':
      return (
        <span className="inline-flex items-center gap-1.5 rounded-md bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 ring-1 ring-amber-700/10 dark:bg-amber-950/60 dark:text-amber-300 dark:ring-amber-400/20">
          {showIcon && <Users className="h-3.5 w-3.5" />}
          Co-location
        </span>
      );
    default:
      return null;
  }
}
