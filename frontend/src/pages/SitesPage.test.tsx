import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import SitesPage from './SitesPage';

describe('SitesPage component', () => {
  it('renders navbar and initial loading state or empty state during SSR/renderToString', () => {
    const html = renderToString(
      <MemoryRouter>
        <SitesPage />
      </MemoryRouter>
    );

    expect(html).toContain('Multi-Audit Trend History');
    expect(html).toContain('Home');
  });
});
