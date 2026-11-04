import { Link } from 'react-router-dom';
import { ShieldCheck, HardHat, ArrowRight } from 'lucide-react';
import type { Template } from '../api/types';
import RuleChip from './RuleChip';

interface TemplateCardProps {
  template: Template;
}

export default function TemplateCard({ template }: TemplateCardProps) {
  const isFire = template.id.includes('fire');
  const isDefault = template.id === 'campus_fire_exit_core';
  const Icon = isFire ? ShieldCheck : HardHat;

  return (
    <div className={`flex flex-col justify-between rounded-2xl border ${isDefault ? 'border-emerald-500/50 bg-gradient-to-b from-emerald-50/20 to-[var(--color-surface)] dark:from-emerald-950/10 ring-1 ring-emerald-500/30' : 'border-[var(--color-border)] bg-[var(--color-surface)]'} p-5 sm:p-6 shadow-sm transition-all duration-200 hover:border-[var(--color-accent)] hover:shadow-md`}>
      <div>
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-3">
            <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${isFire ? 'bg-red-50 text-red-600 dark:bg-red-950/60 dark:text-red-400 ring-1 ring-red-200 dark:ring-red-900/40' : 'bg-blue-50 text-blue-600 dark:bg-blue-950/60 dark:text-blue-400 ring-1 ring-blue-200 dark:ring-blue-900/40'}`}>
              <Icon className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="font-bold text-[var(--color-text)] text-base">
                  {template.name}
                </h3>
                {isDefault ? (
                  <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:text-emerald-300 border border-emerald-500/30">
                    Default (Phone)
                  </span>
                ) : (
                  <span className="rounded-full bg-slate-500/10 px-2 py-0.5 text-[10px] font-medium text-slate-700 dark:text-slate-300 border border-slate-500/20">
                    Experimental
                  </span>
                )}
              </div>
              <span className="text-xs text-[var(--color-text-secondary)]">
                {template.rules.length} verification rules · Evidence-First
              </span>
            </div>
          </div>
        </div>

        <p className="text-xs sm:text-sm text-[var(--color-text-secondary)] leading-relaxed mb-4">
          {template.description}
        </p>

        {/* Rule tags preview */}
        <div className="flex flex-wrap items-center gap-1.5 mb-5">
          {template.rules.slice(0, 3).map((r) => (
            <RuleChip key={r.id} type={r.type} showIcon={false} />
          ))}
          {template.rules.length > 3 && (
            <span className="text-[11px] text-[var(--color-text-secondary)] self-center ml-1 font-mono">
              +{template.rules.length - 3} more
            </span>
          )}
        </div>
      </div>

      <div className="pt-3.5 border-t border-[var(--color-border)] flex items-center justify-between gap-3">
        <span className="text-[11px] font-mono text-[var(--color-text-secondary)] truncate">
          {template.id}
        </span>
        <Link
          to={`/new/${template.id}`}
          className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] px-3.5 py-2 text-xs font-semibold text-white shadow-sm transition-all shrink-0 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] focus:ring-offset-2"
        >
          Select Checklist
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </div>
  );
}
