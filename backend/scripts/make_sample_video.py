"""Synthetic walkthrough video generator for AuditLens.

Generates a 25-second test video containing labeled colored objects:
- Fire Extinguisher (red, mounted)
- Emergency Exit Sign (green, overhead)
- A4 Sheet Scale Reference (white, floor level)
- Obstacle Box (brown, blocking pathway)
- Person (blue, walking)
- Safety Helmet (yellow, on person)
- Secondary Exit Door (cyan, far wall)
"""

from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import cv2


def generate_sample_video(output_path: str | Path, duration_s: int = 25, fps: int = 25) -> Path:
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    width = 1280
    height = 720
    total_frames = duration_s * fps

    # Try mp4v codec
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_file), fourcc, fps, (width, height))

    if not writer.isOpened():
        # Fallback to avc1
        fourcc = cv2.VideoWriter_fourcc(*"avc1")
        writer = cv2.VideoWriter(str(out_file), fourcc, fps, (width, height))

    if not writer.isOpened():
        raise RuntimeError(f"Could not open VideoWriter for {out_file}")

    print(f"Generating {duration_s}s synthetic video ({total_frames} frames) -> {out_file}...")

    font = cv2.FONT_HERSHEY_SIMPLEX

    for frame_idx in range(total_frames):
        t = frame_idx / fps  # timestamp in seconds

        # Background: room with wall (top half, light gray) and floor (bottom half, darker gray)
        img = np.full((height, width, 3), (220, 220, 225), dtype=np.uint8)
        # Floor
        cv2.rectangle(img, (0, 360), (width, height), (170, 175, 180), -1)
        # Horizon / baseboard line
        cv2.line(img, (0, 360), (width, 360), (120, 125, 130), 3)

        # Walkway perspective lines
        cv2.line(img, (400, 360), (200, height), (140, 145, 150), 2)
        cv2.line(img, (880, 360), (1080, height), (140, 145, 150), 2)

        # ── 1. Fire Extinguisher (0s - 9s): Red cylinder on left wall ────
        if 0.5 <= t <= 9.0:
            ext_x, ext_y = 100, 220
            ext_w, ext_h = 70, 130
            cv2.rectangle(img, (ext_x, ext_y), (ext_x + ext_w, ext_y + ext_h), (30, 30, 220), -1)
            cv2.rectangle(img, (ext_x, ext_y), (ext_x + ext_w, ext_y + ext_h), (0, 0, 140), 2)
            cv2.putText(img, "EXTINGUISHER", (ext_x - 15, ext_y - 10), font, 0.5, (0, 0, 200), 2)

        # ── 2. Exit Sign (2s - 15s): Green illuminated sign overhead ─────
        if 2.0 <= t <= 15.0:
            sign_x, sign_y = 560, 80
            sign_w, sign_h = 160, 60
            cv2.rectangle(img, (sign_x, sign_y), (sign_x + sign_w, sign_y + sign_h), (50, 180, 50), -1)
            cv2.rectangle(img, (sign_x, sign_y), (sign_x + sign_w, sign_y + sign_h), (20, 100, 20), 2)
            cv2.putText(img, "EXIT ->", (sign_x + 30, sign_y + 40), font, 0.8, (255, 255, 255), 2)

        # ── 3. A4 Sheet (6s - 19s): White sheet on floor (0.297m ref) ────
        if 6.0 <= t <= 19.0:
            a4_x, a4_y = 480, 500
            a4_w, a4_h = 110, 75
            cv2.rectangle(img, (a4_x, a4_y), (a4_x + a4_w, a4_y + a4_h), (250, 250, 250), -1)
            cv2.rectangle(img, (a4_x, a4_y), (a4_x + a4_w, a4_y + a4_h), (50, 50, 50), 2)
            cv2.putText(img, "A4 REF (0.297m)", (a4_x - 10, a4_y - 10), font, 0.45, (40, 40, 40), 1)

        # ── 4. Obstacle Box (8s - 21s): Brown box blocking walkway ───────
        if 8.0 <= t <= 21.0:
            box_x, box_y = 620, 460
            box_w, box_h = 150, 130
            cv2.rectangle(img, (box_x, box_y), (box_x + box_w, box_y + box_h), (60, 100, 160), -1)
            cv2.rectangle(img, (box_x, box_y), (box_x + box_w, box_y + box_h), (30, 60, 100), 2)
            cv2.putText(img, "OBSTACLE BOX", (box_x - 5, box_y - 10), font, 0.5, (20, 50, 120), 2)

        # ── 5. Person & Helmet (11s - 25s): Worker in workshop ───────────
        if 11.0 <= t <= 25.0:
            # Person moves slowly across frame
            move_prog = (t - 11.0) / 14.0
            p_x = int(220 + move_prog * 450)
            p_y = 260
            p_w, p_h = 120, 260

            # Person body (blue)
            cv2.rectangle(img, (p_x, p_y + 40), (p_x + p_w, p_y + p_h), (180, 100, 50), -1)
            cv2.rectangle(img, (p_x, p_y + 40), (p_x + p_w, p_y + p_h), (120, 60, 20), 2)
            cv2.putText(img, "PERSON", (p_x + 15, p_y + 120), font, 0.6, (255, 255, 255), 2)

            # Safety Helmet (yellow, on top of person)
            h_x = p_x + 15
            h_y = p_y
            h_w = 90
            h_h = 45
            cv2.rectangle(img, (h_x, h_y), (h_x + h_w, h_y + h_h), (30, 210, 230), -1)
            cv2.rectangle(img, (h_x, h_y), (h_x + h_w, h_y + h_h), (10, 140, 160), 2)
            cv2.putText(img, "HELMET", (h_x + 10, h_y - 8), font, 0.45, (0, 140, 180), 2)

        # ── 6. Secondary Exit Door (16s - 25s): Far right doorway ─────────
        if 16.0 <= t <= 25.0:
            door_x, door_y = 1000, 180
            door_w, door_h = 140, 260
            cv2.rectangle(img, (door_x, door_y), (door_x + door_w, door_y + door_h), (180, 210, 180), -1)
            cv2.rectangle(img, (door_x, door_y), (door_x + door_w, door_y + door_h), (60, 120, 60), 3)
            cv2.putText(img, "EXIT DOOR 2", (door_x + 5, door_y - 10), font, 0.5, (40, 100, 40), 2)

        # ── Frame HUD Info (Timestamp & Status) ───────────────────────────
        hud_text = f"AuditLens Test Walkthrough  |  Time: {t:05.2f}s  |  Frame: {frame_idx:04d}/{total_frames}"
        cv2.putText(img, hud_text, (30, 40), font, 0.65, (40, 40, 40), 2)

        writer.write(img)

    writer.release()
    print(f"Sample video created successfully: {out_file} ({out_file.stat().st_size / (1024*1024):.2f} MB)")
    return out_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic sample walkthrough video.")
    parser.add_argument(
        "--output",
        "-o",
        default="./data/sample_walkthrough.mp4",
        help="Target output video file path",
    )
    parser.add_argument("--duration", "-d", type=int, default=25, help="Duration in seconds")
    args = parser.parse_args()

    generate_sample_video(args.output, duration_s=args.duration)
