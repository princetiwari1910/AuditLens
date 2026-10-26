import { describe, expect, it } from 'vitest';
import {
  calculateLetterboxViewport,
  mapNormalizedToLetterboxCanvas,
  mapPolygonToLetterboxCanvas,
} from './coordinates';
import { formatTimestamp, getScoreGrade, getStatusMeta } from './formatters';

describe('Letterbox coordinate mapping', () => {
  it('handles widescreen video inside tall canvas (letterbox top & bottom)', () => {
    // 16:9 video inside 1:1 square canvas (800x800)
    const viewport = calculateLetterboxViewport({
      canvasWidth: 800,
      canvasHeight: 800,
      videoNaturalWidth: 1600,
      videoNaturalHeight: 900,
    });

    expect(viewport.renderWidth).toBe(800);
    expect(viewport.renderHeight).toBe(450); // 800 * 9 / 16 = 450
    expect(viewport.offsetX).toBe(0);
    expect(viewport.offsetY).toBe(175); // (800 - 450) / 2 = 175

    // Project center point (0.5, 0.5)
    const box = mapNormalizedToLetterboxCanvas(
      { x: 0.5, y: 0.5, w: 0.1, h: 0.2 },
      viewport,
    );
    expect(box.x).toBe(400); // 0 + 0.5 * 800
    expect(box.y).toBe(175 + 0.5 * 450); // 175 + 225 = 400
    expect(box.w).toBe(80); // 0.1 * 800
    expect(box.h).toBe(90); // 0.2 * 450
  });

  it('handles vertical portrait video inside wide canvas (pillarbox left & right)', () => {
    // 9:16 vertical video inside 1920x1080 canvas
    const viewport = calculateLetterboxViewport({
      canvasWidth: 1920,
      canvasHeight: 1080,
      videoNaturalWidth: 1080,
      videoNaturalHeight: 1920,
    });

    expect(viewport.renderHeight).toBe(1080);
    expect(viewport.renderWidth).toBe(1080 * (9 / 16)); // 607.5
    expect(viewport.offsetY).toBe(0);
    expect(viewport.offsetX).toBe((1920 - 607.5) / 2); // 656.25
  });

  it('maps polygon coordinates correctly', () => {
    const viewport = { offsetX: 50, offsetY: 20, renderWidth: 400, renderHeight: 200 };
    const poly = mapPolygonToLetterboxCanvas([[0, 0], [1, 1]], viewport);
    expect(poly[0]).toEqual({ x: 50, y: 20 });
    expect(poly[1]).toEqual({ x: 450, y: 220 });
  });
});

describe('Formatters and helpers', () => {
  it('formats timestamps into MM:SS', () => {
    expect(formatTimestamp(0)).toBe('0:00');
    expect(formatTimestamp(7)).toBe('0:07');
    expect(formatTimestamp(65.4)).toBe('1:05');
    expect(formatTimestamp(125)).toBe('2:05');
  });

  it('returns accessible status meta', () => {
    expect(getStatusMeta('pass').label).toBe('PASS');
    expect(getStatusMeta('fail').label).toBe('FAIL');
    expect(getStatusMeta('unsure').label).toBe('NEEDS REVIEW');
  });

  it('calculates score grades', () => {
    expect(getScoreGrade(90).label).toBe('Good Compliance');
    expect(getScoreGrade(65).label).toBe('Action Required');
    expect(getScoreGrade(35).label).toBe('High Risk');
  });
});
