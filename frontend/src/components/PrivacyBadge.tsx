import { Info } from 'lucide-react';

export default function PrivacyBadge() {
  const note =
    'Stored frames and exported evidence are blurred (best effort). The original upload is kept for playback and frames are sent to the model before blurring.';

  return (
    <div
      className="flex items-center gap-2 rounded-xl bg-slate-500/10 px-3.5 py-2 text-xs font-medium text-slate-700 dark:text-slate-300 border border-slate-500/20 print:bg-slate-100 print:border-slate-300 print:text-slate-800"
      title={note}
    >
      <Info className="h-4 w-4 text-slate-500 shrink-0" />
      <span>{note}</span>
    </div>
  );
}
