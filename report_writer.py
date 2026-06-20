"""
Report Writer
=============
Writes image_analysis.json and image_objects.json to the output directory.
"""

import json
from datetime import datetime
from pathlib import Path


class ReportWriter:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_analysis(self, records: list[dict]) -> Path:
        """Write image_analysis.json — metadata for all images."""
        payload = {
            "report_type": "image_metadata_analysis",
            "generated_at": datetime.now().isoformat(),
            "total_images": len(records),
            "images": records,
        }
        path = self.output_dir / "image_analysis.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str, ensure_ascii=False)
        return path

    def write_objects(self, records: list[dict]) -> Path:
        """Write image_objects.json — object detections for all images."""
        # Aggregate summary
        total_detections = sum(r.get("total_detections", 0) for r in records)
        all_categories: dict[str, int] = {}
        for r in records:
            for cat, cnt in (r.get("category_summary") or {}).items():
                all_categories[cat] = all_categories.get(cat, 0) + cnt

        has_weapons_any = any(
            (r.get("intelligence_flags") or {}).get("has_weapons", False)
            for r in records
        )

        payload = {
            "report_type": "image_object_detections",
            "generated_at": datetime.now().isoformat(),
            "total_images": len(records),
            "total_detections_all_images": total_detections,
            "category_totals": all_categories,
            "weapons_detected_in_any_image": has_weapons_any,
            "images": records,
        }
        path = self.output_dir / "image_objects.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str, ensure_ascii=False)
        return path
