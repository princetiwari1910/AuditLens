import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import TracePage from './TracePage';

describe('TracePage component', () => {
  it('renders loading state initially during SSR/renderToString', () => {
    const html = renderToString(
      <MemoryRouter>
        <TracePage />
      </MemoryRouter>
    );

    expect(html).toContain('Loading execution trace');
  });
});
