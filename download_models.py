"""
Model Downloader
================
Run this ONCE before using the system to pre-download YOLOv11 weights.

    python download_models.py
    python download_models.py --model yolo11m.pt
"""

import argparse


def download(model_name: str):
    print(f"Downloading {model_name} via Ultralytics...")
    try:
        from ultralytics import YOLO
        model = YOLO(model_name)
        print(f"✓ {model_name} is ready.")
    except Exception as e:
        print(f"[ERROR] Could not download {model_name}: {e}")
        print("Ensure you have an active internet connection.")
        raise


def main():
    parser = argparse.ArgumentParser(description="Download YOLOv11 model weights")
    parser.add_argument(
        "--model", "-m",
        default="yolo11n.pt",
        choices=["yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11l.pt", "yolo11x.pt"],
        help="Which model to download (default: yolo11n.pt — fastest)"
    )
    args = parser.parse_args()
    download(args.model)
    print()
    print("You can now run:")
    print(f"  python main.py --model {args.model} [images or --folder ...]")


if __name__ == "__main__":
    main()
