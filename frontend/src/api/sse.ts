import { useCallback, useEffect, useRef, useState } from 'react';
import type { SSEEvent } from './types';
import { API_BASE_URL } from './config';
import { getAudit } from './client';

export interface UseAuditEventsReturn {
  events: SSEEvent[];
  isConnected: boolean;
  isCompleted: boolean;
  error: string | null;
  currentRule: string;
  currentTool: string;
  progressPercent: number;
  retry: () => void;
}

export function useAuditEvents(auditId: string | undefined): UseAuditEventsReturn {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isCompleted, setIsCompleted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentRule, setCurrentRule] = useState<string>('');
  const [currentTool, setCurrentTool] = useState<string>('');
  const [progressPercent, setProgressPercent] = useState<number>(5);

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fallbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fallbackPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const eventsCountRef = useRef<number>(0);
  const retryCountRef = useRef<number>(0);
  const activeRef = useRef<boolean>(true);

  const stopPolling = useCallback(() => {
    if (fallbackTimerRef.current) {
      clearTimeout(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }
    if (fallbackPollRef.current) {
      clearInterval(fallbackPollRef.current);
      fallbackPollRef.current = null;
    }
  }, []);

  const handleIncomingEvent = useCallback((eventData: string) => {
    try {
      const parsed: SSEEvent = JSON.parse(eventData);
      if (parsed.type === ('ping' as any)) return;

      eventsCountRef.current += 1;
      stopPolling();

      setEvents((prev) => {
        const exists = prev.some(
          (ev) =>
            ev.type === parsed.type &&
            ev.ts === parsed.ts &&
            JSON.stringify(ev.payload) === JSON.stringify(parsed.payload)
        );
        return exists ? prev : [...prev, parsed];
      });

      // Track progress and current rule
      if (parsed.type === 'audit_started') {
        setProgressPercent(15);
      } else if (parsed.type === 'frames_sampled') {
        setProgressPercent(30);
      } else if (parsed.type === 'tool_call') {
        const rule = (parsed.payload.rule_id as string) || '';
        const tool = (parsed.payload.tool as string) || '';
        if (rule) setCurrentRule(rule);
        if (tool) setCurrentTool(tool);
        setProgressPercent((prev) => Math.min(88, prev + 8));
      } else if (parsed.type === 'finding_recorded') {
        setProgressPercent((prev) => Math.min(94, prev + 5));
      } else if (parsed.type === 'audit_completed') {
        setIsCompleted(true);
        setProgressPercent(100);
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
        }
      } else if (parsed.type === 'error') {
        const msg = (parsed.payload.error as string) || 'Audit failed';
        setError(msg);
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
        }
      }
    } catch {
      // Ignore JSON parse errors for non-JSON heartbeats
    }
  }, [stopPolling]);

  const pollAuditStatus = useCallback(async () => {
    if (!auditId || !activeRef.current) return;
    try {
      const audit = await getAudit(auditId);
      if (!activeRef.current) return;

      if (audit.status === 'completed') {
        setIsCompleted(true);
        setProgressPercent(100);
        stopPolling();
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
        }
      } else if (audit.status === 'failed') {
        setError(audit.error || 'Audit processing failed on backend.');
        stopPolling();
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
        }
      } else if (audit.status === 'processing') {
        // Show steady progress even when relying on polling fallback
        setProgressPercent((prev) => Math.min(90, Math.max(30, prev + 10)));
      }
    } catch (err: any) {
      console.warn('Fallback polling request error:', err);
      if (err?.status === 404 || (err instanceof Error && err.message.includes('404'))) {
        stopPolling();
        setError('Audit not found');
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
        }
      }
    }
  }, [auditId, stopPolling]);

  const connect = useCallback(() => {
    if (!activeRef.current || !auditId) return;

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    const sseUrl = `${API_BASE_URL}/api/audits/${auditId}/events`;
    const es = new EventSource(sseUrl);
    eventSourceRef.current = es;

    // Immediately set connected state as soon as the HTTP connection opens
    es.onopen = () => {
      if (!activeRef.current) return;
      setIsConnected(true);
      setError(null);
      retryCountRef.current = 0;
    };

    // Generic message handler
    es.onmessage = (e) => {
      if (!activeRef.current) return;
      handleIncomingEvent(e.data);
    };

    // Dedicated listeners for custom event types (safety redundancy)
    const eventTypes = [
      'audit_started',
      'frames_sampled',
      'tool_call',
      'tool_result',
      'finding_recorded',
      'audit_completed',
      'error',
      'ping',
    ];
    eventTypes.forEach((type) => {
      es.addEventListener(type, (e: any) => {
        if (!activeRef.current) return;
        handleIncomingEvent(e.data);
      });
    });

    es.onerror = () => {
      if (!activeRef.current) return;
      setIsConnected(false);
      es.close();

      retryCountRef.current += 1;
      if (retryCountRef.current >= 4 && eventsCountRef.current === 0) {
        // If 4 attempts failed without any events, show error with retry option
        setError('Connection to audit event stream interrupted. You can retry or check backend logs.');
      } else {
        // Attempt reconnect with backoff
        reconnectTimeoutRef.current = setTimeout(() => {
          if (activeRef.current) connect();
        }, 1500);
      }
    };

    // Start 5-second fallback timer: if no event arrives within 5s, poll GET /api/audits/{id} every second
    if (!fallbackTimerRef.current && !fallbackPollRef.current) {
      fallbackTimerRef.current = setTimeout(() => {
        if (eventsCountRef.current === 0 && activeRef.current) {
          console.info('SSE idle after 5s: activating fallback polling for audit', auditId);
          pollAuditStatus(); // Immediate first check
          fallbackPollRef.current = setInterval(pollAuditStatus, 1000);
        }
      }, 5000);
    }
  }, [auditId, handleIncomingEvent, pollAuditStatus]);

  const retry = useCallback(() => {
    setError(null);
    setIsConnected(false);
    retryCountRef.current = 0;
    eventsCountRef.current = 0;
    stopPolling();
    connect();
  }, [connect, stopPolling]);

  useEffect(() => {
    activeRef.current = true;
    connect();

    return () => {
      activeRef.current = false;
      stopPolling();
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect, stopPolling]);

  return {
    events,
    isConnected,
    isCompleted,
    error,
    currentRule,
    currentTool,
    progressPercent,
    retry,
  };
}
