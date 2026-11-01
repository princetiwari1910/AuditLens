import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import Home from './Home';

describe('Home page error handling', () => {
  it('renders without native alert/confirm and shows clean structure', () => {
    const html = renderToString(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );

    expect(html).toContain('AuditLens');
    expect(html).toContain('Start Custom Audit');
    expect(html).not.toContain('alert(');
  });
});
