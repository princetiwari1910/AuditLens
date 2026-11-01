import { ShieldCheck } from 'lucide-react';

export default function PrivacyBadge() {
  return (
    <div
      className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
      title="People blurred (best effort): faces and persons are detected and redacted. Missed detections mean missed blur."
    >
      <ShieldCheck className="h-3.5 w-3.5" />
      <span>People blurred (best effort)</span>
    </div>
  );
}
