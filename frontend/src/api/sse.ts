import { useEffect, useRef, useState } from 'react';
import type { SSEEvent } from './types';

export interface UseAuditEventsReturn {
  events: SSEEvent[];
  isConnected: boolean;
  isCompleted: boolean;
  error: string | null;
  currentRule: string;
  currentTool: string;
  progressPercent: number;
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

  useEffect(() => {
    if (!auditId) return;

    let active = true;

    function connect() {
      if (!active) return;
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const es = new EventSource(`/api/audits/${auditId}/events`);
      eventSourceRef.current = es;

      es.onopen = () => {
        if (!active) return;
        setIsConnected(true);
        setError(null);
      };

      es.onmessage = (e) => {
        if (!active) return;
        try {
          const parsed: SSEEvent = JSON.parse(e.data);
          if (parsed.type === ('ping' as any)) return;

          setEvents((prev) => {
            // Avoid duplicate events if replaying
            const exists = prev.some((ev) => ev.type === parsed.type && ev.ts === parsed.ts && JSON.stringify(ev.payload) === JSON.stringify(parsed.payload));
            return exists ? prev : [...prev, parsed];
          });

          // Track progress and current rule
          if (parsed.type === 'audit_started') {
            setProgressPercent(10);
          } else if (parsed.type === 'frames_sampled') {
            setProgressPercent(25);
          } else if (parsed.type === 'tool_call') {
            const rule = (parsed.payload.rule_id as string) || '';
            const tool = (parsed.payload.tool as string) || '';
            if (rule) setCurrentRule(rule);
            if (tool) setCurrentTool(tool);
            setProgressPercent((prev) => Math.min(85, prev + 8));
          } else if (parsed.type === 'finding_recorded') {
            setProgressPercent((prev) => Math.min(92, prev + 6));
          } else if (parsed.type === 'audit_completed') {
            setIsCompleted(true);
            setProgressPercent(100);
            es.close();
          } else if (parsed.type === 'error') {
            const msg = (parsed.payload.error as string) || 'Audit failed';
            setError(msg);
            es.close();
          }
        } catch {
          // Ignore JSON parse errors for heartbeats
        }
      };

      es.onerror = () => {
        if (!active) return;
        setIsConnected(false);
        es.close();
        // If not completed, attempt reconnect after 2s
        if (!isCompleted) {
          reconnectTimeoutRef.current = setTimeout(() => {
            if (active) connect();
          }, 2000);
        }
      };
    }

    connect();

    return () => {
      active = false;
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [auditId]);

  return {
    events,
    isConnected,
    isCompleted,
    error,
    currentRule,
    currentTool,
    progressPercent,
  };
}
