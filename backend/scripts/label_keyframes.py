#!/usr/bin/env python3
"""CLI utility to create and curate per-frame ground truth label files from video keyframes.

Usage:
    python backend/scripts/label_keyframes.py --video data/sample_walkthrough.mp4 --template fire_exit_safety
    python backend/scripts/label_keyframes.py --auto
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure backend root is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import cv2
from app.template_loader import get_template


def sample_keyframes(video_path: Path, fps: float = 1.0) -> list[dict]:
    """Sample keyframes from video with timestamps."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {video_path}")

    video_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(int(round(video_fps / fps)), 1)

    keyframes = []
    frame_idx = 0
    sampled_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % step == 0:
            ts_s = round(frame_idx / video_fps, 2)
            keyframes.append({
                "frame_idx": sampled_count,
                "timestamp_s": ts_s,
                "source_frame": frame_idx,
            })
            sampled_count += 1
        frame_idx += 1

    cap.release()
    return keyframes


def create_labels_file(
    video_path: Path,
    template_id: str = "fire_exit_safety",
    output_path: Path | None = None,
    auto: bool = True,
) -> Path:
    """Generate or update per-frame ground truth label file."""
    tmpl = get_template(template_id)
    if not tmpl:
        raise ValueError(f"Template '{template_id}' not found.")

    keyframes = sample_keyframes(video_path, fps=1.0)
    video_stem = video_path.stem
    if not output_path:
        labels_dir = PROJECT_ROOT / "data" / "labels"
        labels_dir.mkdir(parents=True, exist_ok=True)
        output_path = labels_dir / f"{video_stem}.json"

    # Per-frame rules structure
    rule_ids = [r.id for r in tmpl.rules]
    frames_data = []

    for kf in keyframes:
        frame_labels = {r_id: "unsure" for r_id in rule_ids}
        frames_data.append({
            "frame_idx": kf["frame_idx"],
            "timestamp_s": kf["timestamp_s"],
            "labels": frame_labels,
        })

    # Overall rule labels
    rules_overall = {r_id: "unsure" for r_id in rule_ids}

    # If file exists, merge existing labels
    if output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            rules_overall.update(existing.get("rules", {}))
            existing_frames_map = {f["frame_idx"]: f["labels"] for f in existing.get("frames", [])}
            for fd in frames_data:
                if fd["frame_idx"] in existing_frames_map:
                    fd["labels"].update(existing_frames_map[fd["frame_idx"]])
        except Exception:
            pass

    payload = {
        "video_id": video_stem,
        "template_id": template_id,
        "video_path": str(video_path.relative_to(PROJECT_ROOT) if video_path.is_relative_to(PROJECT_ROOT) else video_path),
        "duration_s": keyframes[-1]["timestamp_s"] if keyframes else 0.0,
        "fps": 1.0,
        "rules": rules_overall,
        "frames": frames_data,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"✅ Ground-truth label file created at: {output_path}")
    print(f"   Total keyframes: {len(frames_data)} | Rules: {len(rule_ids)}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Create per-frame ground truth label files from video keyframes")
    parser.add_argument("--video", default="data/sample_walkthrough.mp4", help="Path to walkthrough video")
    parser.add_argument("--template", default="fire_exit_safety", help="Template ID (e.g. fire_exit_safety, college_lab_safety)")
    parser.add_argument("--output", default=None, help="Output JSON path (defaults to data/labels/<video_id>.json)")
    parser.add_argument("--auto", action="store_true", default=True, help="Automatically initialize draft labels")
    args = parser.parse_args()

    v_path = Path(args.video)
    if not v_path.is_absolute():
        v_path = PROJECT_ROOT / v_path

    if not v_path.exists():
        from scripts.make_sample_video import generate_sample_video
        v_path.parent.mkdir(parents=True, exist_ok=True)
        generate_sample_video(v_path, duration_s=25)

    out_p = Path(args.output) if args.output else None
    create_labels_file(v_path, template_id=args.template, output_path=out_p, auto=args.auto)


if __name__ == "__main__":
    main()
