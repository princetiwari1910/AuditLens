import { describe, it, expect } from 'vitest';
import { renderToString } from 'react-dom/server';
import ReplayBadge, { getReplayBadgeLabel } from './ReplayBadge';

describe('ReplayBadge', () => {
  it('returns null when isReplay is false or undefined', () => {
    const htmlFalse = renderToString(<ReplayBadge isReplay={false} />);
    expect(htmlFalse).toBe('');

    const htmlUndef = renderToString(<ReplayBadge />);
    expect(htmlUndef).toBe('');
  });

  it('renders SIMULATED REPLAY (mock fixtures) for mock or default source_provider_mode', () => {
    const html = renderToString(<ReplayBadge isReplay={true} sourceProviderMode="mock" />);
    expect(html).toContain('SIMULATED REPLAY (mock fixtures)');
    expect(html).toContain('data-testid="replay-badge"');

    const htmlNull = renderToString(<ReplayBadge isReplay={true} sourceProviderMode={null} />);
    expect(htmlNull).toContain('SIMULATED REPLAY (mock fixtures)');
  });

  it('renders compact SIMULATED REPLAY for mock source when compact is true', () => {
    const html = renderToString(<ReplayBadge isReplay={true} sourceProviderMode="mock" compact />);
    expect(html).toContain('SIMULATED REPLAY');
    expect(html).not.toContain('(mock fixtures)');
  });

  it('renders RECORDED RUN (live providers) when source_provider_mode is record', () => {
    const html = renderToString(<ReplayBadge isReplay={true} sourceProviderMode="record" />);
    expect(html).toContain('RECORDED RUN (live providers)');
  });

  it('renders compact RECORDED RUN when source_provider_mode is record and compact is true', () => {
    const html = renderToString(<ReplayBadge isReplay={true} sourceProviderMode="record" compact />);
    expect(html).toContain('RECORDED RUN');
    expect(html).not.toContain('(live providers)');
  });

  it('applies custom className when provided', () => {
    const html = renderToString(
      <ReplayBadge isReplay={true} className="custom-test-badge" />
    );
    expect(html).toContain('class="custom-test-badge"');
  });

  it('helper getReplayBadgeLabel generates correct strings', () => {
    expect(getReplayBadgeLabel('mock', false)).toBe('SIMULATED REPLAY (mock fixtures)');
    expect(getReplayBadgeLabel('mock', true)).toBe('SIMULATED REPLAY');
    expect(getReplayBadgeLabel('record', false)).toBe('RECORDED RUN (live providers)');
    expect(getReplayBadgeLabel('record', true)).toBe('RECORDED RUN');
    expect(getReplayBadgeLabel(undefined, true)).toBe('SIMULATED REPLAY');
  });
});
