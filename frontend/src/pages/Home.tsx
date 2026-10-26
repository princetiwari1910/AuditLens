import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Shield, Upload, ArrowRight, FileCheck } from 'lucide-react';
import { getHealth, type HealthResponse } from '../api/client';

export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    getHealth().then(setHealth).catch(console.error);
  }, []);

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      {/* Header */}
      <header className="border-b border-[var(--color-border)] px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="h-6 w-6 text-[var(--color-accent)]" />
            <span className="text-xl font-semibold text-[var(--color-text)]">
              AuditLens
            </span>
          </div>
          {health && (
            <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-medium text-green-800">
              {health.provider_mode} mode
            </span>
          )}
        </div>
      </header>

      {/* Hero */}
      <main className="mx-auto max-w-5xl px-6 py-12">
        <div className="mb-12 text-center">
          <h1 className="mb-3 text-4xl font-bold text-[var(--color-text)]">
            Safety audits from walkthrough videos
          </h1>
          <p className="mx-auto max-w-2xl text-lg text-[var(--color-text-secondary)]">
            Upload a phone video of your space, pick a checklist, and get an
            evidence-backed report with findings, overlays, and fixes.
          </p>
        </div>

        {/* Template cards */}
        <section className="mb-12">
          <h2 className="mb-4 text-lg font-semibold text-[var(--color-text)]">
            Choose a checklist
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {['fire_exit_safety', 'workshop_ppe'].map((tid) => (
              <Link
                key={tid}
                to={`/new/${tid}`}
                className="group flex items-center justify-between rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[var(--shadow)] transition-shadow hover:shadow-[var(--shadow-md)]"
              >
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <FileCheck className="h-5 w-5 text-[var(--color-accent)]" />
                    <h3 className="font-semibold text-[var(--color-text)]">
                      {tid.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                    </h3>
                  </div>
                  <p className="text-sm text-[var(--color-text-secondary)]">
                    5 rules · Tap to start audit
                  </p>
                </div>
                <ArrowRight className="h-5 w-5 text-[var(--color-text-secondary)] transition-transform group-hover:translate-x-1" />
              </Link>
            ))}
          </div>
        </section>

        {/* Custom rule box */}
        <section className="mb-12">
          <h2 className="mb-4 text-lg font-semibold text-[var(--color-text)]">
            Or write your own rule
          </h2>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="e.g. 'Fire blanket is visible near the stove'"
              className="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-[var(--color-text)] placeholder:text-[var(--color-text-secondary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
            />
            <button className="inline-flex items-center gap-2 rounded-lg bg-[var(--color-accent)] px-5 py-3 font-medium text-white transition-colors hover:bg-[var(--color-accent-hover)]">
              <Upload className="h-4 w-4" />
              Start
            </button>
          </div>
        </section>

        {/* Recent audits */}
        <section>
          <h2 className="mb-4 text-lg font-semibold text-[var(--color-text)]">
            Recent audits
          </h2>
          <p className="text-[var(--color-text-secondary)]">
            No audits yet. Upload a video to get started.
          </p>
        </section>
      </main>
    </div>
  );
}
