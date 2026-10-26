import React from 'react';
import { Link } from 'react-router-dom';
import { ShieldCheck, HardHat, ArrowRight, CheckCircle2 } from 'lucide-react';
import type { Template } from '../api/types';
import RuleChip from './RuleChip';

interface TemplateCardProps {
  template: Template;
}

export default function TemplateCard({ template }: TemplateCardProps) {
  const isFire = template.id.includes('fire');
  const Icon = isFire ? ShieldCheck : HardHat;

  return (
    <div className="flex flex-col justify-between rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-sm transition-all duration-200 hover:border-[var(--color-accent)] hover:shadow-md">
      <div>
        <div className="flex items-start justify-between gap-4 mb-3">
          <div className="flex items-center gap-3">
            <div className={`flex h-11 w-11 items-center justify-center rounded-lg ${isFire ? 'bg-red-50 text-red-600 dark:bg-red-950/60 dark:text-red-400' : 'bg-blue-50 text-blue-600 dark:bg-blue-950/60 dark:text-blue-400'}`}>
              <Icon className="h-6 w-6" />
            </div>
            <div>
              <h3 className="font-semibold text-[var(--color-text)] text-base">
                {template.name}
              </h3>
              <span className="text-xs text-[var(--color-text-secondary)]">
                {template.rules.length} verification rules
              </span>
            </div>
          </div>
        </div>

        <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed mb-4">
          {template.description}
        </p>

        {/* Rule tags preview */}
        <div className="flex flex-wrap gap-1.5 mb-6">
          {template.rules.slice(0, 3).map((r) => (
            <RuleChip key={r.id} type={r.type} showIcon={false} />
          ))}
          {template.rules.length > 3 && (
            <span className="text-xs text-[var(--color-text-secondary)] self-center ml-1">
              +{template.rules.length - 3} more
            </span>
          )}
        </div>
      </div>

      <div className="pt-4 border-t border-[var(--color-border)] flex items-center justify-between">
        <span className="text-xs font-mono text-[var(--color-text-secondary)]">
          {template.id}
        </span>
        <Link
          to={`/new/${template.id}`}
          className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-accent)] px-4 py-2 text-xs font-medium text-white transition-colors hover:bg-[var(--color-accent-hover)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] focus:ring-offset-2"
        >
          Select Checklist
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </div>
  );
}
