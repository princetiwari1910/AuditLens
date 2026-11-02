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

  it('renders "Trends need at least 2 audits" when site has only 1 audit', () => {
    const mockSite = {
      id: 'site_test_01',
      name: 'Single Audit Site',
      location_label: 'Building B',
      audit_count: 1,
    };
    const mockTrends = {
      site: mockSite,
      score_trend: [
        {
          audit_id: 'audit_01',
          created_at: '2026-11-01T12:00:00Z',
          score: 75,
          pass_count: 2,
          fail_count: 1,
          unsure_count: 1,
        },
      ],
      open_issues: [
        {
          finding_id: 'f_01',
          rule_id: 'exit_path_not_blocked',
          status: 'fail',
          severity: 'high',
          rationale: 'Egress pathway blocked by ladder',
          fix_text: 'Remove ladder',
        },
        {
          finding_id: 'f_02',
          rule_id: 'extinguisher_accessible',
          status: 'needs_review',
          severity: 'medium',
          rationale: 'Extinguisher partially obscured by coat rack',
          fix_text: 'Relocate coat rack',
        },
      ],
      recurring_issues: [],
      resolved_issues: [],
      trend_notice: 'Trends need at least 2 audits',
    };
    const mockAudits = [
      {
        id: 'audit_01',
        site_id: 'site_test_01',
        status: 'completed',
        template_id: 'campus_fire_exit_core',
        created_at: '2026-11-01T12:00:00Z',
        summary: { score: 75, pass: 2, fail: 1, unsure: 1 },
      } as any,
    ];

    const html = renderToString(
      <MemoryRouter>
        <SitesPage
          initialSites={[mockSite]}
          initialTrends={mockTrends}
          initialAudits={mockAudits}
        />
      </MemoryRouter>
    );

    // Open deficiencies count equals non-pass (fail + needs_review) = 2
    expect(html).toContain('Open Deficiencies');
    expect(html).toContain('Current Open Deficiencies');
    expect(html).toContain('exit_path_not_blocked');
    expect(html).toContain('extinguisher_accessible');
    expect(html).toContain('FAIL');
    expect(html).toContain('NEEDS REVIEW');

    // With a single audit, show "Trends need at least 2 audits" instead of zeros
    expect(html).toContain('Trends need at least 2 audits');
  });

  it('renders recurring and resolved counts when site has at least 2 audits', () => {
    const mockSite = {
      id: 'site_test_02',
      name: 'Multi Audit Site',
      location_label: 'Building C',
      audit_count: 2,
    };
    const mockTrends = {
      site: mockSite,
      score_trend: [
        {
          audit_id: 'audit_01',
          created_at: '2026-10-01T12:00:00Z',
          score: 50,
          pass_count: 1,
          fail_count: 2,
          unsure_count: 0,
        },
        {
          audit_id: 'audit_02',
          created_at: '2026-11-01T12:00:00Z',
          score: 85,
          pass_count: 3,
          fail_count: 1,
          unsure_count: 0,
        },
      ],
      open_issues: [
        {
          finding_id: 'f_02',
          rule_id: 'extinguisher_visible',
          status: 'fail',
          severity: 'high',
          rationale: 'Extinguisher still missing',
          fix_text: 'Install extinguisher',
        },
      ],
      recurring_issues: [
        { rule_id: 'extinguisher_visible', fail_occurrences: 2 },
      ],
      resolved_issues: [
        { rule_id: 'exit_path_not_blocked', status: 'resolved', note: 'Unobstructed' },
      ],
    };
    const mockAudits = [
      { id: 'audit_01', site_id: 'site_test_02' } as any,
      { id: 'audit_02', site_id: 'site_test_02' } as any,
    ];

    const html = renderToString(
      <MemoryRouter>
        <SitesPage
          initialSites={[mockSite]}
          initialTrends={mockTrends}
          initialAudits={mockAudits}
        />
      </MemoryRouter>
    );

    // Multi-audit displays normal counts
    expect(html).toContain('Recurring Deficiencies');
    expect(html).toContain('Verified Resolved');
    expect(html).toContain('2x failed');
    expect(html).toContain('extinguisher_visible');
  });
});
