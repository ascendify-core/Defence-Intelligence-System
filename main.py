"""
Image Intelligence Extraction System
=====================================
Extracts metadata + performs object detection on JPEG images.
Outputs: image_analysis.json, image_objects.json

Usage:
    python main.py                          # Interactive file picker
    python main.py img1.jpg img2.jpg        # Pass files directly
    python main.py --folder ./my_images     # Process entire folder
"""

import argparse
import sys
from pathlib import Path

from utils.metadata_extractor import MetadataExtractor
from utils.object_detector import ObjectDetector
from utils.report_writer import ReportWriter
from utils.ui import ImageSelector, print_banner, print_summary


def parse_args():
    parser = argparse.ArgumentParser(
        description="Image Intelligence Extraction System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "images",
        nargs="*",
        help="JPEG image file paths to process",
    )
    parser.add_argument(
        "--folder", "-f",
        type=str,
        help="Process all JPEG images in a folder",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="output",
        help="Directory to write JSON output files (default: ./output)",
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default="yolo11n.pt",
        help="YOLOv11 model weights (default: yolo11n.pt). Options: yolo11n.pt, yolo11s.pt, yolo11m.pt, yolo11l.pt, yolo11x.pt",
    )
    parser.add_argument(
        "--confidence", "-c",
        type=float,
        default=0.35,
        help="Detection confidence threshold (default: 0.35)",
    )
    parser.add_argument(
        "--no-annotated",
        action="store_true",
        help="Skip saving annotated images",
    )
    parser.add_argument(
        "--grounding-dino",
        action="store_true",
        help="Also run GroundingDINO for open-vocabulary detection (requires groundingdino installed)",
    )
    return parser.parse_args()


def collect_image_paths(args) -> list[Path]:
    """Collect image paths from args, folder flag, or interactive picker."""
    paths: list[Path] = []

    # From CLI positional args
    if args.images:
        for p in args.images:
            path = Path(p)
            if not path.exists():
                print(f"  [WARN] File not found: {p}")
            elif path.suffix.lower() not in (".jpg", ".jpeg"):
                print(f"  [WARN] Skipping non-JPEG file: {p}")
            else:
                paths.append(path)

    # From --folder
    if args.folder:
        folder = Path(args.folder)
        if not folder.is_dir():
            print(f"[ERROR] Folder not found: {args.folder}")
            sys.exit(1)
        found = sorted(folder.glob("*.jpg")) + sorted(folder.glob("*.jpeg")) + \
                sorted(folder.glob("*.JPG")) + sorted(folder.glob("*.JPEG"))
        if not found:
            print(f"[ERROR] No JPEG images found in: {args.folder}")
            sys.exit(1)
        paths.extend(found)

    # Interactive picker if nothing provided
    if not paths:
        paths = ImageSelector.pick_files()

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for p in paths:
        key = p.resolve()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def main():
    print_banner()
    args = parse_args()

    # ── Collect images ────────────────────────────────────────────────────────
    image_paths = collect_image_paths(args)
    if not image_paths:
        print("[ERROR] No images to process. Exiting.")
        sys.exit(1)

    print(f"\n  Found {len(image_paths)} image(s) to process.\n")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Metadata extraction ───────────────────────────────────────────
    print("=" * 60)
    print("  STEP 1 — Metadata Extraction")
    print("=" * 60)
    extractor = MetadataExtractor()
    analysis_records = []
    for img_path in image_paths:
        print(f"  → {img_path.name}", end=" ", flush=True)
        record = extractor.extract(img_path)
        analysis_records.append(record)
        print("✓")

    # ── Step 2: Object detection ───────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  STEP 2 — Object Detection")
    print("=" * 60)
    detector = ObjectDetector(
        model_name=args.model,
        confidence=args.confidence,
        save_annotated=not args.no_annotated,
        annotated_dir=output_dir / "annotated",
        use_grounding_dino=args.grounding_dino,
    )
    object_records = []
    for img_path in image_paths:
        print(f"  → {img_path.name}", end=" ", flush=True)
        record = detector.detect(img_path)
        object_records.append(record)
        count = record.get("total_detections", 0)
        print(f"✓  ({count} objects detected)")

    # ── Step 3: Write outputs ─────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  STEP 3 — Writing JSON Reports")
    print("=" * 60)
    writer = ReportWriter(output_dir)
    analysis_path = writer.write_analysis(analysis_records)
    objects_path = writer.write_objects(object_records)

    print(f"  → {analysis_path}")
    print(f"  → {objects_path}")

    # ── Summary ────────────────────────────────────────────────────────────────
    print_summary(analysis_records, object_records, output_dir)


if __name__ == "__main__":
    main()
