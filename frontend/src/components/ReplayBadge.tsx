export interface ReplayBadgeProps {
  isReplay?: boolean;
  sourceProviderMode?: string | null;
  compact?: boolean;
  className?: string;
}

export function getReplayBadgeLabel(
  sourceProviderMode?: string | null,
  compact: boolean = false
): string {
  const isLive = sourceProviderMode === 'record';
  if (compact) {
    return isLive ? 'RECORDED RUN' : 'SIMULATED REPLAY';
  }
  return isLive ? 'RECORDED RUN (live providers)' : 'SIMULATED REPLAY (mock fixtures)';
}

export default function ReplayBadge({
  isReplay = false,
  sourceProviderMode,
  compact = false,
  className = 'rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-400 border border-amber-500/30',
}: ReplayBadgeProps) {
  if (!isReplay) return null;

  const label = getReplayBadgeLabel(sourceProviderMode, compact);
  return (
    <span data-testid="replay-badge" className={className}>
      {label}
    </span>
  );
}
