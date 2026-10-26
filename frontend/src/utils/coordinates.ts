/**
 * Exact geometric coordinate projection for letterboxed (object-fit: contain) videos.
 */

export interface LetterboxParams {
  canvasWidth: number;
  canvasHeight: number;
  videoNaturalWidth: number;
  videoNaturalHeight: number;
}

export interface RenderViewport {
  offsetX: number;
  offsetY: number;
  renderWidth: number;
  renderHeight: number;
}

export interface ProjectedBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Point2D {
  x: number;
  y: number;
}

/**
 * Compute the visible active video viewport within an object-fit: contain container.
 */
export function calculateLetterboxViewport(params: LetterboxParams): RenderViewport {
  const { canvasWidth, canvasHeight, videoNaturalWidth, videoNaturalHeight } = params;

  if (
    canvasWidth <= 0 ||
    canvasHeight <= 0 ||
    videoNaturalWidth <= 0 ||
    videoNaturalHeight <= 0
  ) {
    return { offsetX: 0, offsetY: 0, renderWidth: canvasWidth, renderHeight: canvasHeight };
  }

  const videoAspect = videoNaturalWidth / videoNaturalHeight;
  const canvasAspect = canvasWidth / canvasHeight;

  let renderWidth: number;
  let renderHeight: number;
  let offsetX: number;
  let offsetY: number;

  if (videoAspect > canvasAspect) {
    // Video is wider than canvas -> horizontal fit with top/bottom letterbox bars
    renderWidth = canvasWidth;
    renderHeight = canvasWidth / videoAspect;
    offsetX = 0;
    offsetY = (canvasHeight - renderHeight) / 2;
  } else {
    // Canvas is wider than video -> vertical fit with left/right pillarbox bars
    renderHeight = canvasHeight;
    renderWidth = canvasHeight * videoAspect;
    offsetX = (canvasWidth - renderWidth) / 2;
    offsetY = 0;
  }

  return { offsetX, offsetY, renderWidth, renderHeight };
}

/**
 * Project a normalized bounding box ({x, y, w, h} within [0, 1]) to canvas pixel coordinates.
 */
export function mapNormalizedToLetterboxCanvas(
  normBox: { x: number; y: number; w: number; h: number },
  viewport: RenderViewport,
): ProjectedBox {
  const { offsetX, offsetY, renderWidth, renderHeight } = viewport;

  return {
    x: offsetX + normBox.x * renderWidth,
    y: offsetY + normBox.y * renderHeight,
    w: normBox.w * renderWidth,
    h: normBox.h * renderHeight,
  };
}

/**
 * Project a normalized polygon (list of [x, y] in [0, 1]) to canvas pixel coordinates.
 */
export function mapPolygonToLetterboxCanvas(
  normPolygon: number[][],
  viewport: RenderViewport,
): Point2D[] {
  const { offsetX, offsetY, renderWidth, renderHeight } = viewport;

  return normPolygon.map(([nx, ny]) => ({
    x: offsetX + nx * renderWidth,
    y: offsetY + ny * renderHeight,
  }));
}
