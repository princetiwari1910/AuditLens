import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import TemplateCard from './TemplateCard';

describe('TemplateCard component resiliency', () => {
  it('renders standard template without errors', () => {
    const template: any = {
      id: 'campus_fire_exit_core',
      name: 'Campus Fire Exit Core',
      description: 'Test checklist description',
      rules: [
        { id: 'r1', type: 'presence', title: 'Rule 1' },
      ],
    };

    const html = renderToString(
      <MemoryRouter>
        <TemplateCard template={template} />
      </MemoryRouter>
    );

    expect(html).toContain('Campus Fire Exit Core');
    expect(html).toContain('campus_fire_exit_core');
    expect(html).toContain('Default (Phone)');
  });

  it('renders safely without throwing when id or rules are undefined or malformed', () => {
    const malformedTemplate: any = {
      name: 'Malformed Template',
      // id is intentionally missing
      // rules is intentionally missing
    };

    const html = renderToString(
      <MemoryRouter>
        <TemplateCard template={malformedTemplate} />
      </MemoryRouter>
    );

    expect(html).toContain('Malformed Template');
    expect(html).toContain('unknown_template');
    expect(html).toContain('verification rules');
  });

  it('handles null or invalid template without throwing', () => {
    const html = renderToString(
      <MemoryRouter>
        <TemplateCard template={null as any} />
      </MemoryRouter>
    );

    expect(html).toBe('');
  });
});
