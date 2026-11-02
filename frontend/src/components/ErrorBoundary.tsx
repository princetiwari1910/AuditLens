import React, { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertOctagon, RotateCcw, Home as HomeIcon } from 'lucide-react';

export interface ErrorBoundaryProps {
  children: ReactNode;
  fallbackTitle?: string;
  onReset?: () => void;
}

export interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught error:', error, errorInfo);
  }

  handleRetry = () => {
    if (this.props.onReset) {
      this.props.onReset();
    }
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      const errorMessage =
        this.state.error?.message ||
        (typeof this.state.error === 'string' ? this.state.error : 'An unexpected error occurred.');

      return (
        <div
          role="alert"
          className="min-h-screen bg-[var(--color-bg)] flex flex-col items-center justify-center p-6 text-center"
        >
          <div className="w-full max-w-md rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-8 shadow-xl space-y-5">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-500/10 text-rose-600 dark:text-rose-400">
              <AlertOctagon className="h-7 w-7" />
            </div>

            <div className="space-y-2">
              <h1 className="text-xl font-bold tracking-tight text-[var(--color-text)]">
                {this.props.fallbackTitle || 'Something Went Wrong'}
              </h1>
              <p className="text-xs text-[var(--color-text-secondary)] font-mono break-words bg-[var(--color-bg)] p-3 rounded-lg border border-[var(--color-border)] text-left">
                {errorMessage}
              </p>
            </div>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
              <a
                href="/"
                className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-2.5 text-xs font-semibold text-[var(--color-text)] hover:bg-[var(--color-bg-secondary)] transition-colors"
              >
                <HomeIcon className="h-4 w-4" />
                <span>Back to Home</span>
              </a>

              <button
                type="button"
                onClick={this.handleRetry}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 rounded-xl bg-[var(--color-accent)] px-4 py-2.5 text-xs font-semibold text-white hover:bg-[var(--color-accent-hover)] transition-colors cursor-pointer"
              >
                <RotateCcw className="h-4 w-4" />
                <span>Retry</span>
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
