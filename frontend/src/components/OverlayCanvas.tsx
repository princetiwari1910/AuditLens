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
      const rawMeas = finding.measurement as any;
      const normBox = rawMeas?.bbox || { x: 0.15, y: 0.25, w: 0.25, h: 0.4 };

      const projected = mapNormalizedToLetterboxCanvas(normBox, viewport);
      const { x, y, w, h } = projected;

      ctx.save();

      // 1. Semi-transparent bounding fill
      ctx.fillStyle = isSelected ? `${meta.colorHex}26` : `${meta.colorHex}12`;
      ctx.fillRect(x, y, w, h);

      // 2. Subtle connecting boundary box
      ctx.strokeStyle = isSelected ? meta.colorHex : `${meta.colorHex}66`;
      ctx.lineWidth = isSelected ? 2 : 1;
      if (!isSelected) {
        ctx.setLineDash([4, 4]);
      } else {
        ctx.setLineDash([]);
      }
      ctx.strokeRect(x, y, w, h);

      // 3. Technical Corner Reticles (L-brackets at corners, inspired by CV platforms)
      const cornerLen = Math.max(8, Math.min(Math.min(w, h) * 0.25, 18));
      ctx.strokeStyle = meta.colorHex;
      ctx.lineWidth = isSelected ? 3.5 : 2.5;
      ctx.setLineDash([]);
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';

      // Top-Left corner
      ctx.beginPath();
      ctx.moveTo(x, y + cornerLen);
      ctx.lineTo(x, y);
      ctx.lineTo(x + cornerLen, y);
      ctx.stroke();

      // Top-Right corner
      ctx.beginPath();
      ctx.moveTo(x + w - cornerLen, y);
      ctx.lineTo(x + w, y);
      ctx.lineTo(x + w, y + cornerLen);
      ctx.stroke();

      // Bottom-Left corner
      ctx.beginPath();
      ctx.moveTo(x, y + h - cornerLen);
      ctx.lineTo(x, y + h);
      ctx.lineTo(x + cornerLen, y + h);
      ctx.stroke();

      // Bottom-Right corner
      ctx.beginPath();
      ctx.moveTo(x + w - cornerLen, y + h);
      ctx.lineTo(x + w, y + h);
      ctx.lineTo(x + w, y + h - cornerLen);
      ctx.stroke();

      // 4. CV Status Pill Badge with Dot
      const label = `${meta.label}: ${finding.rule_id} (${Math.round(finding.confidence * 100)}%)`;
      ctx.font = '600 11px ui-monospace, SFMono-Regular, Menlo, monospace';
      const textWidth = ctx.measureText(label).width;

      const badgeX = Math.max(viewport.offsetX + 4, x);
      const badgeY = Math.max(viewport.offsetY + 18, y - 6);
      const pillWidth = textWidth + 24;
      const pillHeight = 20;

      // Draw pill background with border
      ctx.fillStyle = '#090d16ee';
      ctx.strokeStyle = meta.colorHex;
      ctx.lineWidth = 1;

      // Rounded rectangle for pill
      const r = 4;
      ctx.beginPath();
      ctx.moveTo(badgeX + r, badgeY - 14);
      ctx.lineTo(badgeX + pillWidth - r, badgeY - 14);
      ctx.quadraticCurveTo(badgeX + pillWidth, badgeY - 14, badgeX + pillWidth, badgeY - 14 + r);
      ctx.lineTo(badgeX + pillWidth, badgeY - 14 + pillHeight - r);
      ctx.quadraticCurveTo(badgeX + pillWidth, badgeY - 14 + pillHeight, badgeX + pillWidth - r, badgeY - 14 + pillHeight);
      ctx.lineTo(badgeX + r, badgeY - 14 + pillHeight);
      ctx.quadraticCurveTo(badgeX, badgeY - 14 + pillHeight, badgeX, badgeY - 14 + pillHeight - r);
      ctx.lineTo(badgeX, badgeY - 14 + r);
      ctx.quadraticCurveTo(badgeX, badgeY - 14, badgeX + r, badgeY - 14);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // Indicator dot
      ctx.fillStyle = meta.colorHex;
      ctx.beginPath();
      ctx.arc(badgeX + 8, badgeY - 4, 3.5, 0, Math.PI * 2);
      ctx.fill();

      // Text label
      ctx.fillStyle = '#f8fafc';
      ctx.fillText(label, badgeX + 16, badgeY);

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
