import { AlertTriangle } from 'lucide-react';

interface DisclaimerProps {
  compact?: boolean;
}

export default function Disclaimer({ compact = false }: DisclaimerProps) {
  if (compact) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2 text-xs text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200">
        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <span>
          <strong>Assistive pre-audit tool:</strong> Does not certify legal compliance. Always verify with official inspectors.
        </span>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-amber-200/90 bg-amber-50/80 p-4 text-sm text-amber-950 shadow-sm dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200 print:border-slate-300 print:bg-white print:text-slate-800">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400 print:text-slate-600" />
        <div className="space-y-1">
          <p className="font-semibold text-amber-900 dark:text-amber-100 print:text-black">
            Assistive Pre-Audit Disclaimer
          </p>
          <p className="text-xs leading-relaxed text-amber-800/90 dark:text-amber-300/80 print:text-slate-700">
            AuditLens is designed to assist teams identify safety oversights prior to official inspections.
            It does not replace legal certification or qualified professional audits. All measurements are optical approximations
            subject to camera perspective and depth variance.
          </p>
        </div>
      </div>
    </div>
  );
}
