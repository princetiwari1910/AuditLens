import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import FixPlanSection from './FixPlanSection';

describe('FixPlanSection component', () => {
  it('renders loading state initially during SSR/renderToString', () => {
    const html = renderToString(
      <FixPlanSection auditId="audit_test_123" />
    );

    expect(html).toContain('Generating prioritized corrective action plan');
  });
});
