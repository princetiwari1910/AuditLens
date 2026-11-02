import { describe, expect, it, vi } from 'vitest';
import { renderToString } from 'react-dom/server';
import ErrorBoundary from './ErrorBoundary';

function ProblemChild(): never {
  throw new Error('Test crash in child component');
}

describe('ErrorBoundary component', () => {
  it('renders children when no error occurs', () => {
    const html = renderToString(
      <ErrorBoundary>
        <div>Normal content</div>
      </ErrorBoundary>
    );

    expect(html).toContain('Normal content');
  });

  it('renders error message, Back to Home link, and Retry button on error', () => {
    // Suppress expected console.error during ErrorBoundary test
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    // Test ErrorBoundary with state forced or simulated error
    const boundary = new ErrorBoundary({ children: null, fallbackTitle: 'Audit Report Error' });
    boundary.state = { hasError: true, error: new Error('Render failed: undefined field') };
    const rendered = boundary.render() as React.ReactElement;
    const html = renderToString(rendered);

    expect(html).toContain('Audit Report Error');
    expect(html).toContain('Render failed: undefined field');
    expect(html).toContain('Back to Home');
    expect(html).toContain('Retry');
    expect(html).not.toBe('');

    spy.mockRestore();
  });
});
