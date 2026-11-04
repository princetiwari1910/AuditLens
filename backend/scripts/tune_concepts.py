#!/usr/bin/env python3
"""CLI utility to test concept wording against image keyframes and print confidences."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import cv2
import numpy as np

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.providers import get_segmentation_provider
from app.providers.meta import validate_concept


def main() -> int:
    parser = argparse.ArgumentParser(description="Tune and compare SAM concept wording on test images.")
    parser.add_argument(
        "--images",
        "-i",
        default="",
        help="Comma-separated image file paths (e.g. img1.jpg,img2.jpg)",
    )
    parser.add_argument(
        "--concepts",
        "-c",
        default="fire extinguisher,red fire extinguisher cylinder,wall mounted fire extinguisher",
        help="Comma-separated list of noun-phrase concepts (max 5 words each)",
    )
    args = parser.parse_args()

    # Parse concepts
    raw_concepts = [c.strip() for c in args.concepts.split(",") if c.strip()]
    if not raw_concepts:
        print("Error: No concepts provided. Specify via --concepts='concept1,concept2'")
        return 1

    concepts = []
    for c in raw_concepts:
        try:
            validated = validate_concept(c)
            concepts.append(validated)
        except Exception as exc:
            print(f"Invalid concept '{c}': {exc}")
            return 1

    # Parse images
    image_paths: list[Path] = []
    if args.images:
        for p_str in args.images.split(","):
            p = Path(p_str.strip())
            if not p.exists():
                print(f"Error: image file not found: {p}")
                return 1
            image_paths.append(p)
    else:
        # Default test image if none provided
        data_dir = get_settings().DATA_DIR
        data_dir.mkdir(parents=True, exist_ok=True)
        default_img = data_dir / "sample_concept_test.jpg"
        if not default_img.exists():
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.rectangle(img, (200, 100), (350, 400), (0, 0, 220), -1)
            cv2.putText(img, "FIRE EXT", (210, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imwrite(str(default_img), img)
        image_paths.append(default_img)

    seg_provider = get_segmentation_provider()

    print("=" * 100)
    print("  AuditLens Concept Tuning Tool")
    print(f"  Images:   {[p.name for p in image_paths]}")
    print(f"  Concepts: {concepts}")
    print("=" * 100)
    print(f"{'CONCEPT':<36} | {'IMAGE':<18} | {'CONFIDENCE':<10} | {'BOUNDING BOX {x, y, w, h}'}")
    print("-" * 100)

    for img_path in image_paths:
        for concept in concepts:
            try:
                # Segment image for concept
                detections = seg_provider.segment(img_path, [concept])
                if detections:
                    best = max(detections, key=lambda d: getattr(d, "score", 0.0))
                    score_str = f"{best.score:.0%}"
                    box = best.box
                    box_str = f"x={box.get('x',0):.2f}, y={box.get('y',0):.2f}, w={box.get('w',0):.2f}, h={box.get('h',0):.2f}"
                else:
                    score_str = "0% (none)"
                    box_str = "-"
                print(f"{concept:<36} | {img_path.name:<18} | {score_str:<10} | {box_str}")
            except Exception as exc:
                print(f"{concept:<36} | {img_path.name:<18} | {'ERROR':<10} | {exc}")

    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
