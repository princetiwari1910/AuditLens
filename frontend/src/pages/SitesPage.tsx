import { useState, useEffect } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import {
  Building2,
  TrendingUp,
  AlertOctagon,
  CheckCircle2,
  RefreshCw,
  ArrowLeft,
  ChevronRight,
  Clock,
  Layers,
  MapPin,
} from 'lucide-react';
import {
  getSites,
  getSiteTrends,
  getSiteAudits,
  type Site,
  type SiteTrends,
} from '../api/client';
import type { Audit } from '../api/types';
import { getScoreGrade } from '../utils/formatters';

export default function SitesPage() {
  const { id: siteIdParam } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>('');
  const [trends, setTrends] = useState<SiteTrends | null>(null);
  const [audits, setAudits] = useState<Audit[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Load sites list
  useEffect(() => {
    getSites()
      .then((data) => {
        setSites(data);
        if (data.length > 0) {
          const currentId = siteIdParam && data.some((s) => s.id === siteIdParam)
            ? siteIdParam
            : data[0].id;
          setSelectedSiteId(currentId);
        }
      })
      .catch(console.error);
  }, [siteIdParam]);

  // Load site trends and audits whenever selectedSiteId changes
  useEffect(() => {
    if (!selectedSiteId) return;
    setIsLoading(true);

    Promise.all([
      getSiteTrends(selectedSiteId),
      getSiteAudits(selectedSiteId),
    ])
      .then(([trendsData, auditsData]) => {
        setTrends(trendsData);
        setAudits(auditsData);
        setIsLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load site trends:', err);
        setIsLoading(false);
      });
  }, [selectedSiteId]);

  const handleSelectSite = (newSiteId: string) => {
    setSelectedSiteId(newSiteId);
    navigate(`/sites/${newSiteId}`, { replace: true });
  };

  const selectedSite = sites.find((s) => s.id === selectedSiteId) || trends?.site;

  return (
    <div className="min-h-screen bg-[var(--color-bg)] pb-20">
      {/* Top Navbar */}
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-4 sticky top-0 z-20 print:hidden">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Home
          </Link>

          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold text-[var(--color-text)] flex items-center gap-1.5">
              <Building2 className="h-4 w-4 text-indigo-500" />
              <span>Multi-Audit Trend History</span>
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8 space-y-8">
        {/* Site Header & Switcher */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-sm">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-500/10 text-indigo-500">
              <Building2 className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-[var(--color-text)]">
                {selectedSite?.name || 'Facilities & Sites'}
              </h1>
              <p className="text-xs text-[var(--color-text-secondary)] flex items-center gap-1 mt-0.5">
                <MapPin className="h-3.5 w-3.5 text-slate-400" />
                <span>{selectedSite?.location_label || 'Default Facility Location'}</span>
                <span className="mx-1">·</span>
                <span className="font-mono">{audits.length} total inspections</span>
              </p>
            </div>
          </div>

          {/* Site Selector Dropdown */}
          {sites.length > 1 && (
            <div className="flex items-center gap-2">
              <label htmlFor="site-select" className="text-xs font-medium text-[var(--color-text-secondary)]">
                Site:
              </label>
              <select
                id="site-select"
                value={selectedSiteId}
                onChange={(e) => handleSelectSite(e.target.value)}
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1.5 text-xs text-[var(--color-text)] focus:border-[var(--color-accent)] focus:outline-none"
              >
                {sites.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.location_label})
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <RefreshCw className="h-6 w-6 animate-spin text-[var(--color-accent)]" />
          </div>
        ) : !trends ? (
          <div className="rounded-xl border border-dashed border-[var(--color-border)] p-12 text-center text-sm text-[var(--color-text-secondary)]">
            No audit history available for this site yet.
          </div>
        ) : (
          <>
            {/* Quick Metrics Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
                <span className="text-xs text-[var(--color-text-secondary)] flex items-center gap-1">
                  <TrendingUp className="h-3.5 w-3.5 text-blue-500" />
                  Latest Score
                </span>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="text-2xl font-black text-[var(--color-text)]">
                    {trends.score_trend.length > 0
                      ? trends.score_trend[trends.score_trend.length - 1].score
                      : '—'}
                  </span>
                  <span className="text-xs text-[var(--color-text-secondary)]">/ 100</span>
                </div>
              </div>

              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
                <span className="text-xs text-[var(--color-text-secondary)] flex items-center gap-1">
                  <AlertOctagon className="h-3.5 w-3.5 text-rose-500" />
                  Open Deficiencies
                </span>
                <span className="mt-1 text-2xl font-black text-rose-600 dark:text-rose-400 block">
                  {trends.open_issues.length}
                </span>
              </div>

              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
                <span className="text-xs text-[var(--color-text-secondary)] flex items-center gap-1">
                  <RefreshCw className="h-3.5 w-3.5 text-amber-500" />
                  Recurring Issues
                </span>
                <span className="mt-1 text-2xl font-black text-amber-600 dark:text-amber-400 block">
                  {trends.recurring_issues.length}
                </span>
              </div>

              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
                <span className="text-xs text-[var(--color-text-secondary)] flex items-center gap-1">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                  Resolved Deficiencies
                </span>
                <span className="mt-1 text-2xl font-black text-emerald-600 dark:text-emerald-400 block">
                  {trends.resolved_issues.length}
                </span>
              </div>
            </div>

            {/* Score Trend Visual Progression */}
            {trends.score_trend.length > 0 && (
              <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 space-y-4 shadow-sm">
                <h3 className="font-bold text-sm text-[var(--color-text)] flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-blue-500" />
                  <span>Historical Compliance Progression</span>
                </h3>

                <div className="space-y-3 pt-2">
                  {trends.score_trend.map((pt, idx) => {
                    const grade = getScoreGrade(pt.score);
                    return (
                      <div
                        key={pt.audit_id}
                        className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)] text-xs"
                      >
                        <div className="flex items-center gap-3">
                          <span className="font-mono text-[11px] text-[var(--color-text-secondary)]">
                            #{idx + 1}
                          </span>
                          <span className="font-semibold text-[var(--color-text)]">
                            {new Date(pt.created_at).toLocaleDateString()}
                          </span>
                          <span className="font-mono text-[11px] text-[var(--color-text-secondary)]">
                            ({pt.pass_count} pass · {pt.fail_count} fail · {pt.unsure_count} review)
                          </span>
                        </div>

                        <div className="flex items-center gap-4">
                          <div className="w-32 bg-slate-200 dark:bg-slate-700 h-2 rounded-full overflow-hidden">
                            <div
                              className="bg-[var(--color-accent)] h-full rounded-full"
                              style={{ width: `${pt.score}%` }}
                            />
                          </div>
                          <span className={`font-mono font-bold px-2 py-0.5 rounded ${grade.colorClass}`}>
                            {pt.score}/100
                          </span>
                          <Link
                            to={`/audits/${pt.audit_id}`}
                            className="text-[var(--color-accent)] hover:underline flex items-center gap-0.5 font-medium"
                          >
                            <span>Report</span>
                            <ChevronRight className="h-3 w-3" />
                          </Link>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            {/* Deficiencies Deep Dive: Open, Recurring, Resolved */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Open Issues */}
              <div className="rounded-xl border border-rose-200 dark:border-rose-900/50 bg-[var(--color-surface)] p-5 space-y-3">
                <h4 className="font-bold text-xs uppercase tracking-wider text-rose-700 dark:text-rose-400 flex items-center gap-1.5">
                  <AlertOctagon className="h-4 w-4" />
                  <span>Current Open Issues ({trends.open_issues.length})</span>
                </h4>
                {trends.open_issues.length === 0 ? (
                  <p className="text-xs text-[var(--color-text-secondary)] italic">
                    Zero open failure deficiencies in latest inspection.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {trends.open_issues.map((iss) => (
                      <div
                        key={iss.finding_id}
                        className="p-3 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-xs space-y-1"
                      >
                        <div className="font-semibold text-[var(--color-text)]">
                          {iss.rule_id}
                        </div>
                        <p className="text-[11px] text-[var(--color-text-secondary)]">
                          {iss.rationale}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Recurring Issues */}
              <div className="rounded-xl border border-amber-200 dark:border-amber-900/50 bg-[var(--color-surface)] p-5 space-y-3">
                <h4 className="font-bold text-xs uppercase tracking-wider text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
                  <RefreshCw className="h-4 w-4" />
                  <span>Recurring Deficiencies ({trends.recurring_issues.length})</span>
                </h4>
                {trends.recurring_issues.length === 0 ? (
                  <p className="text-xs text-[var(--color-text-secondary)] italic">
                    No repeated failure patterns detected across audits.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {trends.recurring_issues.map((rec) => (
                      <div
                        key={rec.rule_id}
                        className="p-3 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-xs flex items-center justify-between"
                      >
                        <span className="font-semibold text-[var(--color-text)]">
                          {rec.rule_id}
                        </span>
                        <span className="rounded-full bg-amber-500/10 text-amber-700 dark:text-amber-300 px-2 py-0.5 text-[10px] font-mono font-bold">
                          {rec.fail_occurrences}x failed
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Resolved Issues */}
              <div className="rounded-xl border border-emerald-200 dark:border-emerald-900/50 bg-[var(--color-surface)] p-5 space-y-3">
                <h4 className="font-bold text-xs uppercase tracking-wider text-emerald-700 dark:text-emerald-400 flex items-center gap-1.5">
                  <CheckCircle2 className="h-4 w-4" />
                  <span>Verified Resolved ({trends.resolved_issues.length})</span>
                </h4>
                {trends.resolved_issues.length === 0 ? (
                  <p className="text-xs text-[var(--color-text-secondary)] italic">
                    No verified remediations recorded yet.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {trends.resolved_issues.map((res, i) => (
                      <div
                        key={i}
                        className="p-3 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] text-xs space-y-1"
                      >
                        <div className="font-semibold text-emerald-700 dark:text-emerald-300">
                          {res.rule_id}
                        </div>
                        <p className="text-[10px] text-[var(--color-text-secondary)]">
                          {res.note}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Historical Audits List */}
            <section className="space-y-3">
              <h3 className="font-bold text-sm text-[var(--color-text)] flex items-center gap-2">
                <Clock className="h-4 w-4 text-[var(--color-accent)]" />
                <span>Site Inspection History ({audits.length})</span>
              </h3>

              <div className="space-y-2.5">
                {audits.map((a) => (
                  <div
                    key={a.id}
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] hover:border-slate-300 transition-colors"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-xs text-[var(--color-text)]">
                          {a.template_id}
                        </span>
                        {a.is_replay && (
                          <span className="rounded-full bg-amber-500/10 px-1.5 py-0.2 text-[9px] font-bold text-amber-700 dark:text-amber-300">
                            REPLAY
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-[var(--color-text-secondary)] font-mono">
                        {a.id.slice(0, 16)} · {a.created_at ? new Date(a.created_at).toLocaleString() : 'Recent'}
                      </p>
                    </div>

                    <div className="flex items-center gap-3">
                      {a.summary && (
                        <span className="font-mono text-xs font-bold text-[var(--color-text)]">
                          Score: {a.summary.score}/100
                        </span>
                      )}
                      <Link
                        to={`/audits/${a.id}`}
                        className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1.5 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)]"
                      >
                        View Report
                      </Link>
                      <Link
                        to={`/compare?before=${a.id}`}
                        className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-1.5 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)]"
                      >
                        <Layers className="h-3.5 w-3.5 text-[var(--color-accent)]" />
                        Compare
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
