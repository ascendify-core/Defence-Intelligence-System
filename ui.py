"""
UI Utilities
============
Interactive file picker (tkinter), banner, and summary output.
"""

from pathlib import Path


def print_banner():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║         IMAGE INTELLIGENCE EXTRACTION SYSTEM            ║")
    print("║  Metadata · Object Detection · GPS · Device Info        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()


def print_summary(analysis_records: list[dict], object_records: list[dict], output_dir: Path):
    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  Images processed : {len(analysis_records)}")

    # GPS stats
    gps_count = sum(1 for r in analysis_records if r.get("gps"))
    print(f"  Images with GPS  : {gps_count}")

    # Device stats
    devices = set()
    for r in analysis_records:
        dev = r.get("device") or {}
        make = dev.get("make", "")
        model = dev.get("model", "")
        if make or model:
            devices.add(f"{make} {model}".strip())
    if devices:
        print(f"  Devices detected : {', '.join(sorted(devices))}")

    # Detection totals
    total_det = sum(r.get("total_detections", 0) for r in object_records)
    print(f"  Total objects    : {total_det}")

    # Category breakdown
    all_cats: dict[str, int] = {}
    for r in object_records:
        for cat, cnt in (r.get("category_summary") or {}).items():
            all_cats[cat] = all_cats.get(cat, 0) + cnt

    if all_cats:
        print("\n  Category Breakdown:")
        for cat in sorted(all_cats, key=lambda x: -all_cats[x]):
            bar = "█" * min(all_cats[cat], 30)
            print(f"    {cat:<18} {all_cats[cat]:>4}  {bar}")

    # Intelligence flags
    any_weapons = any(
        (r.get("intelligence_flags") or {}).get("has_weapons") for r in object_records
    )
    any_aircraft = any(
        (r.get("intelligence_flags") or {}).get("has_aircraft") for r in object_records
    )
    any_ships = any(
        (r.get("intelligence_flags") or {}).get("has_ships") for r in object_records
    )

    flags_hit = []
    if any_weapons:
        flags_hit.append("⚠ WEAPONS detected")
    if any_aircraft:
        flags_hit.append("✈ Aircraft detected")
    if any_ships:
        flags_hit.append("⛴ Ships detected")

    if flags_hit:
        print()
        print("  Intelligence Flags:")
        for f in flags_hit:
            print(f"    {f}")

    print()
    print(f"  Output directory : {output_dir.resolve()}")
    print("=" * 60)
    print()


class ImageSelector:
    """Provides an interactive file picker using tkinter."""

    @staticmethod
    def pick_files() -> list[Path]:
        """Open a tkinter file dialog to select JPEG images. Falls back to CLI input."""
        print("  No images specified. Opening file picker...")
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.lift()
            root.attributes("-topmost", True)

            file_paths = filedialog.askopenfilenames(
                title="Select JPEG Images",
                filetypes=[
                    ("JPEG Images", "*.jpg *.jpeg *.JPG *.JPEG"),
                    ("All Files", "*.*"),
                ],
            )
            root.destroy()

            if not file_paths:
                print("  No files selected in dialog.")
                return _cli_fallback()

            paths = [Path(p) for p in file_paths]
            print(f"  Selected {len(paths)} file(s) via dialog.")
            return paths

        except Exception as e:
            print(f"  [WARN] File dialog not available ({e}). Falling back to CLI.")
            return _cli_fallback()


def _cli_fallback() -> list[Path]:
    """Ask user to type file paths one by one."""
    print()
    print("  Enter image file paths (one per line).")
    print("  Press ENTER on an empty line when done.")
    print()
    paths = []
    while True:
        try:
            line = input("  File path: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            break
        p = Path(line)
        if not p.exists():
            print(f"    [WARN] File not found: {line}")
        elif p.suffix.lower() not in (".jpg", ".jpeg"):
            print(f"    [WARN] Not a JPEG: {line}")
        else:
            paths.append(p)
            print(f"    Added: {p.name}")
    return paths
