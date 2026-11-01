"""Unit tests for WP4 Privacy Redaction (best-effort person blurring)."""

from pathlib import Path
import cv2
import numpy as np
import pytest

from app.agent.privacy import blur_masked_region, redact_person_detections, redact_frame_image
from app.config import get_settings
from app.frames import sample_frames_from_images, sample_frames_from_video
from app.providers.base import SegmentDetection


class MockPersonSegmenter:
    """Mock segmenter returning a deterministic person detection."""
    def __init__(self, box=None, polygon=None):
        self.box = box or {"x": 0.25, "y": 0.25, "w": 0.5, "h": 0.5}
        self.polygon = polygon

    def segment(self, image, text_prompts):
        if "person" in [p.lower() for p in text_prompts]:
            return [
                SegmentDetection(
                    label="person",
                    box=self.box,
                    score=0.92,
                    mask=self.polygon,
                    frame_id=0,
                    timestamp_s=0.0,
                )
            ]
        return []


def test_blur_masked_region_modifies_only_masked_pixels():
    """Verify that blur_masked_region alters masked pixels while outside pixels remain strictly identical."""
    # Create high-frequency checkerboard pattern
    h, w = 120, 120
    img = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            if (x // 10 + y // 10) % 2 == 0:
                img[y, x] = [255, 255, 255]
            else:
                img[y, x] = [0, 0, 0]

    # Polygon mask in center: [0.3, 0.3] to [0.7, 0.7]
    poly = [[0.3, 0.3], [0.7, 0.3], [0.7, 0.7], [0.3, 0.7]]
    redacted = blur_masked_region(img, polygon=poly, ksize=25)

    # Compute binary mask
    mask = np.zeros((h, w), dtype=np.uint8)
    pts = np.array([[int(p[0] * w), int(p[1] * h)] for p in poly], dtype=np.int32)
    cv2.fillPoly(mask, [pts], 255)

    # Inside mask: pixels must be modified
    inside_mask = mask == 255
    assert not np.array_equal(redacted[inside_mask], img[inside_mask]), "Pixels inside mask must change due to blur"

    # Outside mask: pixels must be byte-for-byte identical
    outside_mask = mask == 0
    assert np.array_equal(redacted[outside_mask], img[outside_mask]), "Pixels outside mask must not change"


def test_blur_with_bbox_modifies_only_bbox_pixels():
    """Verify bbox blurring only alters bbox region."""
    h, w = 100, 100
    img = np.zeros((h, w, 3), dtype=np.uint8)
    # High contrast noise pattern
    np.random.seed(42)
    img[:] = np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)

    bbox = {"x": 0.2, "y": 0.2, "w": 0.4, "h": 0.4}
    redacted = blur_masked_region(img, bbox=bbox, ksize=21)

    bx = int(0.2 * w)
    by = int(0.2 * h)
    bw = int(0.4 * w)
    bh = int(0.4 * h)

    # Inside bbox: changed
    inside = redacted[by : by + bh, bx : bx + bw]
    orig_inside = img[by : by + bh, bx : bx + bw]
    assert not np.array_equal(inside, orig_inside)

    # Outside bbox: corners must be identical
    assert np.array_equal(redacted[0:15, 0:15], img[0:15, 0:15])
    assert np.array_equal(redacted[85:100, 85:100], img[85:100, 85:100])


def test_unblurred_original_never_persisted(tmp_path, monkeypatch):
    """Verify that unblurred original frames are never persisted to disk when PRIVACY_MODE is enabled."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    s = get_settings()
    monkeypatch.setattr(s, "DATA_DIR", data_dir)
    monkeypatch.setattr(s, "PRIVACY_MODE", True)

    # Create test input image with distinct noise
    h, w = 100, 100
    orig = np.zeros((h, w, 3), dtype=np.uint8)
    orig[25:75, 25:75] = 200  # Central patch
    orig[40:60, 40:60] = 50   # Center face pattern

    input_img_path = tmp_path / "input.jpg"
    cv2.imwrite(str(input_img_path), orig)

    mock_seg = MockPersonSegmenter(box={"x": 0.25, "y": 0.25, "w": 0.5, "h": 0.5})

    frames = sample_frames_from_images(
        [input_img_path],
        audit_id="audit_privacy_test",
        segmenter=mock_seg,
    )
    assert len(frames) == 1
    saved_path = Path(frames[0].path)
    assert saved_path.exists()

    # Read the persisted frame from disk
    saved_img = cv2.imread(str(saved_path))
    # The center region (person) MUST be blurred on disk
    center_disk = saved_img[40:60, 40:60]
    center_orig = orig[40:60, 40:60]
    assert not np.array_equal(center_disk, center_orig), "Persisted frame must contain blurred person"

    # Confirm there are no hidden unblurred backup files in the frames directory
    frames_dir = saved_path.parent
    all_stored_files = list(frames_dir.iterdir())
    assert len(all_stored_files) == 1, f"Expected only the redacted frame file, found: {all_stored_files}"


def test_privacy_mode_flag_disables_blurring(tmp_path, monkeypatch):
    """When PRIVACY_MODE is False, frames are persisted without redaction."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    s = get_settings()
    monkeypatch.setattr(s, "DATA_DIR", data_dir)
    monkeypatch.setattr(s, "PRIVACY_MODE", False)

    h, w = 80, 80
    orig = np.ones((h, w, 3), dtype=np.uint8) * 150
    orig[20:60, 20:60] = 50
    input_path = tmp_path / "input_no_priv.jpg"
    cv2.imwrite(str(input_path), orig)

    mock_seg = MockPersonSegmenter(box={"x": 0.2, "y": 0.2, "w": 0.5, "h": 0.5})
    frames = sample_frames_from_images(
        [input_path],
        audit_id="audit_no_privacy",
        segmenter=mock_seg,
    )
    saved_img = cv2.imread(frames[0].path)
    # Since PRIVACY_MODE is False, person region is not blurred (except standard compression loss)
    diff = np.abs(saved_img.astype(float) - orig.astype(float))
    assert np.mean(diff) < 2.0
