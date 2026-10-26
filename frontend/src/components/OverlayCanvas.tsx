import { useEffect, useRef } from 'react';
import type { Finding } from '../api/types';
import {
  calculateLetterboxViewport,
  mapNormalizedToLetterboxCanvas,
} from '../utils/coordinates';
import { getStatusMeta } from '../utils/formatters';

interface OverlayCanvasProps {
  videoElement: HTMLVideoElement | null;
  findings: Finding[];
  selectedFindingId: string | null;
  currentTime: number;
}

export default function OverlayCanvas({
  videoElement,
  findings,
  selectedFindingId,
  currentTime,
}: OverlayCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !videoElement) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Synchronize canvas buffer resolution with CSS client display dimensions
    const width = videoElement.clientWidth;
    const height = videoElement.clientHeight;

    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    ctx.clearRect(0, 0, width, height);

    const naturalWidth = videoElement.videoWidth || 1280;
    const naturalHeight = videoElement.videoHeight || 720;

    // Calculate letterboxing / pillarboxing viewport
    const viewport = calculateLetterboxViewport({
      canvasWidth: width,
      canvasHeight: height,
      videoNaturalWidth: naturalWidth,
      videoNaturalHeight: naturalHeight,
    });

    // Determine findings to render:
    // Either currently selected finding OR findings active within +/- 1.2 seconds of currentTime
    const visibleFindings = findings.filter((f) => {
      if (selectedFindingId && f.id === selectedFindingId) return true;
      return Math.abs(f.timestamp_s - currentTime) <= 1.2;
    });

    visibleFindings.forEach((finding) => {
      const isSelected = finding.id === selectedFindingId;
      const meta = getStatusMeta(finding.status);

      // Extract bbox / polygon if measurement or visual data attached
      // In AuditLens findings, normalized coordinates are derived from detection
      const rawMeas = finding.measurement as any;
      const normBox = rawMeas?.bbox || { x: 0.15, y: 0.25, w: 0.25, h: 0.4 };

      const projected = mapNormalizedToLetterboxCanvas(normBox, viewport);

      ctx.save();

      // Bounding box styling
      ctx.strokeStyle = meta.colorHex;
      ctx.lineWidth = isSelected ? 4 : 2.5;
      if (!isSelected) {
        ctx.setLineDash([6, 4]);
      } else {
        ctx.setLineDash([]);
      }

      // Draw box
      ctx.strokeRect(projected.x, projected.y, projected.w, projected.h);

      // Semitransparent fill on selected finding
      if (isSelected) {
        ctx.fillStyle = `${meta.colorHex}22`; // ~13% opacity
        ctx.fillRect(projected.x, projected.y, projected.w, projected.h);
      }

      // Draw label badge
      const label = `${meta.label}: ${finding.rule_id} (${Math.round(finding.confidence * 100)}%)`;
      ctx.font = 'bold 12px ui-monospace, SFMono-Regular, Menlo, monospace';
      const textWidth = ctx.measureText(label).width;

      const badgeX = Math.max(viewport.offsetX, projected.x);
      const badgeY = Math.max(viewport.offsetY + 16, projected.y - 6);

      ctx.fillStyle = meta.colorHex;
      ctx.fillRect(badgeX, badgeY - 14, textWidth + 12, 18);

      ctx.fillStyle = '#ffffff';
      ctx.fillText(label, badgeX + 6, badgeY);

      ctx.restore();
    });
  }, [videoElement, findings, selectedFindingId, currentTime]);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 h-full w-full"
    />
  );
}
